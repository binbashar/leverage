"""
    Utilities to obtain relevant files' and directories' locations
"""

import os
import pathlib
from pathlib import Path
from subprocess import CalledProcessError
from subprocess import PIPE
from subprocess import run

import hcl2

from leverage._utils import ExitError


class NotARepositoryError(RuntimeError):
    """When you are not running inside a git repository directory"""


def get_working_path():
    """Get the interpreters current directory.

    Returns:
        str: Current working directory.
    """
    return Path.cwd().as_posix()


def get_home_path():
    """Get the current user's home directory.

    Returns:
        str: User's home directory.
    """
    return Path.home().as_posix()


def get_root_path():
    """Get the path to the root of the Git repository.

    Raises:
        NotARepositoryError: If the current directory is not within a git repository.

    Returns:
        str: Root of the repository.
    """
    try:
        root = run(
            ["git", "rev-parse", "--show-toplevel"], stdout=PIPE, stderr=PIPE, check=True, encoding="utf-8"
        ).stdout

    except CalledProcessError as exc:
        if "fatal: not a git repository" in exc.stderr:
            raise NotARepositoryError("Not running in a git repository.")
    except FileNotFoundError as exc:
        raise NotARepositoryError("Not running in a git repository.")
    else:
        return root.strip()


def get_account_path():
    """Get the path to the current account directory.

    Returns:
        str: Path to the current account directory.
    """
    root_path = Path(get_root_path())
    cur_path = Path(get_working_path())
    prev_path = cur_path

    # NOTE: currently we only support up to 8 subdir levels. Normally we use
    #       only 2 subdirectories so this should be enough for most cases.
    for _ in range(8):
        if cur_path.resolve() == root_path:
            break

        prev_path = cur_path
        cur_path = cur_path.parent

    return prev_path.as_posix()


def get_global_config_path():
    """Get the path to the config that is common to all accounts.

    Returns:
        str: Global config file path.
    """
    return f"{get_root_path()}/config"


def get_account_config_path():
    """Get the path to the config of the current account.

    Returns:
        str: Current config file path.
    """
    return f"{get_account_path()}/config"


def get_build_script_path(filename="build.py"):
    """Get path to the build script containing all tasks to be run.
    Search through the current directory up to the repository's root directory.

    Args:
        filename (str, optional): The name of the build script containing the tasks.
            Defaults to "build.py".

    Returns:
        str: Build script file path. None if no file with the given name is found or
            the current directory is not a git repository.
    """
    try:
        root_path = Path(get_root_path())
    except NotARepositoryError:
        script = Path(filename)
        return script.absolute().as_posix() if script.exists() else None

    cur_path = Path(get_working_path())

    while True:
        build_script = list(cur_path.glob(filename))

        if build_script:
            return build_script[0].as_posix()

        if cur_path == root_path:
            break

        cur_path = cur_path.parent


class PathsHandler:
    COMMON_TF_VARS = "common.tfvars"
    ACCOUNT_TF_VARS = "account.tfvars"
    BACKEND_TF_VARS = "backend.tfvars"

    def __init__(self, env_conf: dict, container_user: str):
        self.container_user = container_user
        self.home = Path.home()
        self.cwd = Path.cwd()
        try:
            # TODO: just call get_root_path once and use it to initiate the rest of variables?
            self.root_dir = Path(get_root_path())
            self.account_dir = Path(get_account_path())
            self.common_config_dir = Path(get_global_config_path())
            self.account_config_dir = Path(get_account_config_path())
        except NotARepositoryError:
            raise ExitError(1, "Out of Leverage project context. Please cd into a Leverage project directory first.")

        # TODO: move the confs into a Config class
        common_config = self.common_config_dir / self.COMMON_TF_VARS
        self.common_conf = hcl2.loads(common_config.read_text()) if common_config.exists() else {}

        account_config = self.account_config_dir / self.ACCOUNT_TF_VARS
        self.account_conf = hcl2.loads(account_config.read_text()) if account_config.exists() else {}

        # Get project name
        self.project = self.common_conf.get("project", env_conf.get("PROJECT", False))
        if not self.project:
            raise ExitError(1, "Project name has not been set. Exiting.")

        # Project mount location
        self.project_long = self.common_conf.get("project_long", "project")
        self.guest_base_path = f"/{self.project_long}"

        # Ensure credentials directory
        self.host_aws_credentials_dir = self.home / ".aws" / self.project
        if not self.host_aws_credentials_dir.exists():
            self.host_aws_credentials_dir.mkdir(parents=True)
        self.sso_cache = self.host_aws_credentials_dir / "sso" / "cache"

    def update_cwd(self, new_cwd):
        self.cwd = new_cwd
        acc_folder = new_cwd.relative_to(self.root_dir).parts[0]

        self.account_config_dir = self.root_dir / acc_folder / "config"
        account_config_path = self.account_config_dir / self.ACCOUNT_TF_VARS
        self.account_conf = hcl2.loads(account_config_path.read_text())

    @property
    def guest_account_base_path(self):
        return f"{self.guest_base_path}/{self.account_dir.relative_to(self.root_dir).as_posix()}"

    @property
    def common_tfvars(self):
        return f"{self.guest_base_path}/config/{self.COMMON_TF_VARS}"

    @property
    def account_tfvars(self):
        return f"{self.guest_account_base_path}/config/{self.ACCOUNT_TF_VARS}"

    @property
    def backend_tfvars(self):
        return f"{self.guest_account_base_path}/config/{self.BACKEND_TF_VARS}"

    @property
    def guest_aws_credentials_dir(self):
        return str(f"/home/{self.container_user}/tmp" / Path(self.project))

    @property
    def host_aws_profiles_file(self):
        return f"{self.host_aws_credentials_dir}/config"

    @property
    def host_aws_credentials_file(self):
        return self.host_aws_credentials_dir / "credentials"

    @property
    def host_git_config_file(self):
        return self.home / ".gitconfig"

    @property
    def local_backend_tfvars(self):
        return self.account_config_dir / self.BACKEND_TF_VARS

    @property
    def sso_token_file(self):
        return f"{self.sso_cache}/token"

    def get_location_type(self):
        """
        Returns the location type:
        - root
        - account
        - config
        - layer
        - sublayer
        - not a project
        """
        if self.cwd == self.root_dir:
            return "root"
        elif self.cwd == self.account_dir:
            return "account"
        elif self.cwd in (self.common_config_dir, self.account_config_dir):
            return "config"
        elif (self.cwd.as_posix().find(self.account_dir.as_posix()) >= 0) and list(self.cwd.glob("*.tf")):
            return "layer"
        elif (self.cwd.as_posix().find(self.account_dir.as_posix()) >= 0) and not list(self.cwd.glob("*.tf")):
            return "layers-group"
        else:
            return "not a project"

    def assert_running_leverage_project(self):
        if self.root_dir == self.account_dir == self.common_config_dir == self.account_config_dir == self.cwd:
            raise ExitError(1, "Not running in a Leverage project. Exiting.")

    def guest_config_file(self, file):
        """Map config file in host to location in guest.

        Args:
            file (pathlib.Path): File in host to map

        Raises:
            Exit: If file is not contained in any valid config directory

        Returns:
            str: Path in guest to config file
        """
        file_name = file.name

        if file.parent == self.account_config_dir:
            return f"{self.guest_account_base_path}/config/{file_name}"
        if file.parent == self.common_config_dir:
            return f"{self.guest_base_path}/config/{file_name}"

        raise ExitError(1, "File is not part of any config directory.")

    @property
    def tf_cache_dir(self):
        return os.getenv("TF_PLUGIN_CACHE_DIR")

    def check_for_layer_location(self, path: Path = None):
        """Make sure the command is being run at layer level. If not, bail."""
        path = path or self.cwd
        if path in (self.common_config_dir, self.account_config_dir):
            raise ExitError(1, "Currently in a configuration directory, no Terraform command can be run here.")

        if path in (self.root_dir, self.account_dir):
            raise ExitError(
                1,
                "Terraform commands cannot run neither in the root of the project or in"
                " the root directory of an account.",
            )

        if not list(path.glob("*.tf")):
            raise ExitError(1, "This command can only run at [bold]layer[/bold] level.")

    def check_for_cluster_layer(self, path: Path = None):
        path = path or self.cwd
        self.check_for_layer_location(path)
        # assuming the "cluster" layer will contain the expected EKS outputs
        if path.parts[-1] != "cluster":
            raise ExitError(1, "This command can only run at the [bold]cluster layer[/bold].")


def get_project_root_or_current_dir_path() -> Path:
    """Returns the project root if detected, otherwise the current path"""
    try:
        root = Path(get_root_path())
    except (NotARepositoryError, TypeError):
        root = Path.cwd()

    return root
