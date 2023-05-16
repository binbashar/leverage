import json
import os
import pwd
import re
import webbrowser
from pathlib import Path
from datetime import datetime
from time import sleep

import hcl2
from click.exceptions import Exit
import dockerpty
from docker import DockerClient
from docker.errors import APIError, NotFound
from docker.types import Mount
from typing import Tuple, Union, List

from leverage import __toolbox_version__
from leverage import logger
from leverage._utils import AwsCredsEntryPoint, CustomEntryPoint, ExitError, ContainerSession
from leverage.logger import console, raw_logger
from leverage.logger import get_script_log_level
from leverage.path import get_root_path
from leverage.path import get_account_path
from leverage.path import get_global_config_path
from leverage.path import get_account_config_path
from leverage.path import NotARepositoryError
from leverage.conf import load as load_env

REGION = (
    r"(.*)"  # project folder
    # start region
    r"(global|(?:[a-z]{2}-(?:gov-)?"
    r"(?:central|north|south|east|west|northeast|northwest|southeast|southwest|secret|topsecret)-[1-4]))"
    # end region
    r"(.*)"  # layer
)

raw_logger = raw_logger()


def get_docker_client():
    """Attempt to get a Docker client from the environment configuration. Halt application otherwise.

    Raises:
        Exit: If communication to Docker server could not be established.

    Returns:
        docker.DockerClient: Client for Docker daemon.
    """
    try:
        docker_client = DockerClient.from_env()
        docker_client.ping()

    except:
        logger.error(
            "Docker daemon doesn't seem to be responding. "
            "Please check it is up and running correctly before re-running the command."
        )
        raise Exit(1)

    return docker_client


class LeverageContainer:
    """Basic Leverage Container. Holds the minimum information required to run the Docker image that Leverage uses
    to perform its operations. Commands can be issued as interactive via `start` for when live output or user input is desired
    or the can be simply executed via `exec` to run silently and retrieve the command output.

    NOTE: An aggregation approach to this design should be considered instead of the current inheritance approach.
    """

    LEVERAGE_IMAGE = "binbash/leverage-toolbox"

    COMMON_TFVARS = "common.tfvars"
    ACCOUNT_TFVARS = "account.tfvars"
    BACKEND_TFVARS = "backend.tfvars"

    SHELL = "/bin/bash"

    def __init__(self, client):
        """Project related paths are determined and stored. Project configuration is loaded.

        Args:
            client (docker.DockerClient): Client to interact with Docker daemon.
        """
        self.client = client

        self.home = Path.home()
        self.cwd = Path.cwd()
        try:
            self.root_dir = Path(get_root_path())
            self.account_dir = Path(get_account_path())
            self.common_config_dir = Path(get_global_config_path())
            self.account_config_dir = Path(get_account_config_path())
        except NotARepositoryError:
            logger.error("Out of Leverage project context. Please cd into a Leverage project directory first.")
            raise Exit(1)

        # Load configs
        self.env_conf = load_env()

        common_config = self.common_config_dir / self.COMMON_TFVARS
        self.common_conf = hcl2.loads(common_config.read_text()) if common_config.exists() else {}

        account_config = self.account_config_dir / self.ACCOUNT_TFVARS
        self.account_conf = hcl2.loads(account_config.read_text()) if account_config.exists() else {}

        # Set image to use
        self.image = self.env_conf.get("TERRAFORM_IMAGE", self.LEVERAGE_IMAGE)
        self.image_tag = self.env_conf.get("TERRAFORM_IMAGE_TAG")
        if not self.image_tag:
            logger.error(
                "No docker image tag defined.\n"
                "Please set `TERRAFORM_IMAGE_TAG` variable in the project's [bold]build.env[/bold] file before running a Leverage command."
            )
            raise Exit(1)

        # Get project name
        self.project = self.common_conf.get("project", self.env_conf.get("PROJECT", False))
        if not self.project:
            logger.error("Project name has not been set. Exiting.")
            raise Exit(1)

        # Project mount location
        self.guest_base_path = f"/{self.common_conf.get('project_long', 'project')}"

        # Ensure credentials directory
        self.host_aws_credentials_dir = self.home / ".aws" / self.project
        if not self.host_aws_credentials_dir.exists():
            self.host_aws_credentials_dir.mkdir(parents=True)
        self.sso_cache = self.host_aws_credentials_dir / "sso" / "cache"

        self.host_config = self.client.api.create_host_config(security_opt=["label:disable"], mounts=[])
        self.container_config = {
            "image": f"{self.image}:{self.image_tag}",
            "command": "",
            "stdin_open": True,
            "environment": {},
            "entrypoint": "",
            "working_dir": f"{self.guest_base_path}/{self.cwd.relative_to(self.root_dir).as_posix()}",
            "host_config": self.host_config,
        }

    @property
    def environment(self):
        return self.container_config["environment"]

    @environment.setter
    def environment(self, value):
        self.container_config["environment"] = value

    @property
    def entrypoint(self):
        return self.container_config["entrypoint"]

    @entrypoint.setter
    def entrypoint(self, value):
        self.container_config["entrypoint"] = value

    @property
    def mounts(self):
        return self.container_config["host_config"]["Mounts"]

    @mounts.setter
    def mounts(self, value):
        self.container_config["host_config"]["Mounts"] = value

    @property
    def guest_account_base_path(self):
        return f"{self.guest_base_path}/{self.account_dir.relative_to(self.root_dir).as_posix()}"

    @property
    def common_tfvars(self):
        return f"{self.guest_base_path}/config/{self.COMMON_TFVARS}"

    @property
    def account_tfvars(self):
        return f"{self.guest_account_base_path}/config/{self.ACCOUNT_TFVARS}"

    @property
    def backend_tfvars(self):
        return f"{self.guest_account_base_path}/config/{self.BACKEND_TFVARS}"

    @property
    def guest_aws_credentials_dir(self):
        return f"/root/tmp/{self.project}"

    @property
    def region(self):
        """
        Return the region of the layer.
        """
        if matches := re.match(REGION, self.cwd.as_posix()):
            # the region (group 1) is between the projects folders (group 0) and the layers (group 2)
            return matches.groups()[1]

        logger.exception(f"No valid region could be found at: {self.cwd.as_posix()}")
        raise Exit(1)

    def ensure_image(self):
        """Make sure the required Docker image is available in the system. If not, pull it from registry."""
        found_image = self.client.api.images(f"{self.image}:{self.image_tag}")
        if found_image:
            return

        logger.info("Required Docker image not found.")

        try:
            stream = self.client.api.pull(repository=self.image, tag=self.image_tag, stream=True, decode=True)
        except NotFound as e:
            logger.error(
                f"The specified toolbox version, '{self.image_tag}' (toolbox image '{self.image}:{self.image_tag}') can not be found. "
                "If you come from a project created with an older version of Leverage CLI or have modified the 'build.env' file manually, "
                f"please consider either deleting the file, or configuring a valid toolbox version to use. (i.e. 'TERRAFORM_IMAGE_TAG={__toolbox_version__}')"
            )
            raise Exit(1)
        except APIError as pull:
            pull.__traceback__ = None
            pull.__context__.__traceback__ = None
            logger.exception("Error pulling image:", exc_info=pull)
            raise Exit(1)
        except Exception as e:
            logger.error(f"Not handled error while pulling the image: {e}")
            raise Exit(1)

        logger.info(next(stream)["status"])

        imageinfo = []
        with console.status("Pulling image..."):
            for status in stream:
                status = status["status"]
                if status.startswith("Digest") or status.startswith("Status"):
                    imageinfo.append(status)

        for info in imageinfo:
            logger.info(info)

    def _create_container(self, tty, command="", *args):
        """Create the container that will run the command.

        Args:
            tty (bool): Whether the container will run interactively or not.
            command (str, optional): Command to run. Defaults to "".

        Raises:
            Exit: If the container could not be created.

        Returns:
            dict: Reference to the created container.
        """
        command = " ".join([command] + list(args))
        logger.debug(f"[bold cyan]Running command:[/bold cyan] {command}")
        self.container_config["command"] = command
        self.container_config["tty"] = tty

        try:
            return self.client.api.create_container(**self.container_config)

        except APIError as exc:
            exc.__traceback__ = None
            exc.__context__.__traceback__ = None
            logger.exception("Error creating container:", exc_info=exc)
            raise Exit(1)

    def _run(self, container, run_func):
        """Apply the given run function to the given container, return its outputs and handle container cleanup.

        Args:
            container (dict): Reference to a Docker container.
            run_func (function): Function to apply to the given container.

        Returns:
            any: Whatever the given function returns.
        """
        try:
            return run_func(self.client, container)

        except APIError as exc:
            exc.__traceback__ = None
            exc.__context__.__traceback__ = None
            logger.exception("Error during container execution:", exc_info=exc)

        finally:
            self.client.api.stop(container)
            self.client.api.remove_container(container)

    def _start(self, command: str, *args):
        """Create an interactive container, and run command with the given arguments.

        Args:
            command: Command to run.

        Returns:
            int: Execution exit code.
        """
        container = self._create_container(True, command, *args)

        def run_func(client, container):
            dockerpty.start(client=client.api, container=container)
            return client.api.inspect_container(container)["State"]["ExitCode"]

        return self._run(container, run_func)

    def _start_with_output(self, command, *args):
        """
        Same than _start but also returns the outputs (by dumping the logs) of the container.
        """
        container = self._create_container(True, command, *args)

        def run_func(client, container):
            dockerpty.start(client=client.api, container=container)
            exit_code = client.api.inspect_container(container)["State"]["ExitCode"]
            logs = client.api.logs(container).decode("utf-8")
            return exit_code, logs

        return self._run(container, run_func)

    def start(self, command: str, *arguments) -> int:
        """Run command with the given arguments in an interactive container.
        Returns execution exit code.
        """
        return self._start(command, *arguments)

    def _exec(self, command: str, *args) -> Tuple[int, str]:
        """Create a non interactive container and execute command with the given arguments.
        Returns execution exit code and output.
        """
        container = self._create_container(False, command, *args)

        def run_func(client, container):
            client.api.start(container)
            exit_code = client.api.wait(container)["StatusCode"]
            output = client.api.logs(container).decode("utf-8")
            return exit_code, output

        return self._run(container, run_func)

    def exec(self, command: str, *arguments) -> Tuple[int, str]:
        """Execute command with the given arguments in a container.
        Returns execution exit code and output.
        """
        return self._exec(command, *arguments)

    def docker_logs(self, container):
        return self.client.api.logs(container).decode("utf-8")

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

    def change_ownership_cmd(self, path: Union[Path, str], recursive=True) -> str:
        recursive = "-R " if recursive else ""
        user_id = os.getuid()
        group_id = os.getgid()

        return f"chown {user_id}:{group_id} {recursive}{path}"

    def change_file_ownership(self, path: Union[Path, str], recursive=True):
        """
        Change the file/folder ownership from the internal docker user (usually root)
        to the user executing the CLI.
        """
        cmd = self.change_ownership_cmd(path, recursive=recursive)
        with CustomEntryPoint(self, entrypoint=""):
            self._exec(cmd)


class AWSCLIContainer(LeverageContainer):
    """Leverage Container specially tailored to run AWS CLI commands."""

    AWS_CLI_BINARY = "/usr/local/bin/aws"

    # SSO scripts
    AWS_SSO_LOGIN_SCRIPT = "/root/scripts/aws-sso/aws-sso-login.sh"
    AWS_SSO_LOGOUT_SCRIPT = "/root/scripts/aws-sso/aws-sso-logout.sh"
    AWS_SSO_CONFIGURE_SCRIPT = "/root/scripts/aws-sso/aws-sso-configure.sh"

    # SSO constants
    AWS_SSO_LOGIN_URL = "https://device.sso.{region}.amazonaws.com/?user_code={user_code}"
    AWS_SSO_CODE_WAIT_SECONDS = 2
    AWS_SSO_CODE_ATTEMPTS = 10
    FALLBACK_LINK_MSG = "Opening the browser... if it fails, open this link in your browser:\n{link}"

    def __init__(self, client):
        super().__init__(client)

        self.environment = {
            "COMMON_CONFIG_FILE": self.common_tfvars,
            "ACCOUNT_CONFIG_FILE": self.account_tfvars,
            "BACKEND_CONFIG_FILE": self.backend_tfvars,
            "AWS_SHARED_CREDENTIALS_FILE": f"{self.guest_aws_credentials_dir}/credentials",
            "AWS_CONFIG_FILE": f"{self.guest_aws_credentials_dir}/config",
            "SSO_CACHE_DIR": f"{self.guest_aws_credentials_dir}/sso/cache",
            "SCRIPT_LOG_LEVEL": get_script_log_level(),
        }
        self.entrypoint = self.AWS_CLI_BINARY
        self.mounts = [
            Mount(source=self.root_dir.as_posix(), target=self.guest_base_path, type="bind"),
            Mount(source=self.host_aws_credentials_dir.as_posix(), target=self.guest_aws_credentials_dir, type="bind"),
        ]

        logger.debug(f"[bold cyan]Container configuration:[/bold cyan]\n{json.dumps(self.container_config, indent=2)}")

    def start(self, command, profile=""):
        args = [] if not profile else ["--profile", profile]
        return self._start(command, *args)

    # FIXME: we have a context manager for this now, remove this method later!
    def system_start(self, command):
        """Momentarily override the container's default entrypoint. To run arbitrary commands and not only AWS CLI ones."""
        self.entrypoint = ""
        exit_code = self._start(command)
        self.entrypoint = self.AWS_CLI_BINARY
        return exit_code

    def exec(self, command, profile=""):
        args = [] if not profile else ["--profile", profile]
        return self._exec(command, *args)

    # FIXME: we have a context manager for this now, remove this method later!
    def system_exec(self, command):
        """Momentarily override the container's default entrypoint. To run arbitrary commands and not only AWS CLI ones."""
        self.entrypoint = ""
        exit_code, output = self._exec(command)

        self.entrypoint = self.AWS_CLI_BINARY
        return exit_code, output

    def get_sso_code(self, container) -> str:
        """
        Find and return the SSO user code by periodically checking the logs.
        Up until N attempts.
        """
        logger.info("Fetching SSO code...")
        for _ in range(self.AWS_SSO_CODE_ATTEMPTS):
            # pull logs periodically until we find our SSO code
            logs = self.docker_logs(container)
            if "Then enter the code:" in logs:
                return logs.split("Then enter the code:")[1].split("\n")[2]

            sleep(self.AWS_SSO_CODE_WAIT_SECONDS)

        raise ExitError(1, "Get SSO code timed-out")

    def get_sso_region(self):
        # TODO: what about using the .region property we have now? that takes the value from the path of the layer
        _, region = self.exec(f"configure get sso_region --profile {self.project}-sso")
        return region

    def sso_login(self) -> int:
        region = self.get_sso_region()

        with CustomEntryPoint(self, ""):
            container = self._create_container(False, command=self.AWS_SSO_LOGIN_SCRIPT)

        with ContainerSession(self.client, container):
            # once inside this block, the SSO_LOGIN_SCRIPT is being executed in the "background"
            # now let's grab the user code from the logs
            user_code = self.get_sso_code(container)
            # with the user code, we can now autocomplete the url
            link = self.AWS_SSO_LOGIN_URL.format(region=region.strip(), user_code=user_code)
            webbrowser.open_new_tab(link)
            # The SSO code is only valid once: if the browser was able to open it, the fallback link will be invalid
            logger.info(self.FALLBACK_LINK_MSG.format(link=link))
            # now let's wait until the command locking the container resolve itself:
            # aws sso login will wait for the user code
            # once submitted to the browser, the authentication finish and the lock is released
            exit_code = self.client.api.wait(container)["StatusCode"]
            raw_logger.info(self.docker_logs(container))
            # now return ownership of the token file back to the user
            self.change_file_ownership(self.guest_aws_credentials_dir)

        return exit_code


class TerraformContainer(LeverageContainer):
    """Leverage container specifically tailored to run Terraform commands.
    It handles authentication and some checks regarding where the command is being executed."""

    TF_BINARY = "/bin/terraform"

    TF_MFA_ENTRYPOINT = "/root/scripts/aws-mfa/aws-mfa-entrypoint.sh"
    TF_SSO_ENTRYPOINT = "/root/scripts/aws-sso/aws-sso-entrypoint.sh"

    def __init__(self, client):
        super().__init__(client)

        if self.root_dir == self.account_dir == self.common_config_dir == self.account_config_dir == self.cwd:
            logger.error("Not running in a Leverage project. Exiting.")
            raise Exit(1)

        # Set authentication methods
        self.sso_enabled = self.common_conf.get("sso_enabled", False)
        self.mfa_enabled = (
            self.env_conf.get("MFA_ENABLED", "false") == "true"
        )  # TODO: Convert values to bool upon loading

        # SSH AGENT
        SSH_AUTH_SOCK = os.getenv("SSH_AUTH_SOCK")

        self.environment = {
            "COMMON_CONFIG_FILE": self.common_tfvars,
            "ACCOUNT_CONFIG_FILE": self.account_tfvars,
            "BACKEND_CONFIG_FILE": self.backend_tfvars,
            "AWS_SHARED_CREDENTIALS_FILE": f"{self.guest_aws_credentials_dir}/credentials",
            "AWS_CONFIG_FILE": f"{self.guest_aws_credentials_dir}/config",
            "SRC_AWS_SHARED_CREDENTIALS_FILE": f"{self.guest_aws_credentials_dir}/credentials",  # Legacy?
            "SRC_AWS_CONFIG_FILE": f"{self.guest_aws_credentials_dir}/config",  # Legacy?
            "AWS_CACHE_DIR": f"{self.guest_aws_credentials_dir}/cache",
            "SSO_CACHE_DIR": f"{self.guest_aws_credentials_dir}/sso/cache",
            "SCRIPT_LOG_LEVEL": get_script_log_level(),
            "MFA_SCRIPT_LOG_LEVEL": get_script_log_level(),  # Legacy
            "SSH_AUTH_SOCK": "" if SSH_AUTH_SOCK is None else "/ssh-agent",
        }
        self.entrypoint = self.TF_BINARY
        self.mounts = [
            Mount(source=self.root_dir.as_posix(), target=self.guest_base_path, type="bind"),
            Mount(source=self.host_aws_credentials_dir.as_posix(), target=self.guest_aws_credentials_dir, type="bind"),
            Mount(source=(self.home / ".gitconfig").as_posix(), target="/etc/gitconfig", type="bind"),
        ]
        # if you have set the tf plugin cache locally
        if self.tf_cache_dir:
            # then mount it too into the container
            self.environment["TF_PLUGIN_CACHE_DIR"] = self.tf_cache_dir
            # given that terraform use symlinks to point from the .terraform folder into the plugin folder
            # we need to use the same directory inside the container
            # otherwise symlinks will be broken once outside the container
            # which will break terraform usage outside Leverage
            self.mounts.append(Mount(source=self.tf_cache_dir, target=self.tf_cache_dir, type="bind"))
        if SSH_AUTH_SOCK is not None:
            self.mounts.append(Mount(source=SSH_AUTH_SOCK, target="/ssh-agent", type="bind"))

        self._backend_key = None

        logger.debug(f"[bold cyan]Container configuration:[/bold cyan]\n{json.dumps(self.container_config, indent=2)}")

    @property
    def tf_cache_dir(self):
        return os.getenv("TF_PLUGIN_CACHE_DIR")

    def _guest_config_file(self, file):
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

        logger.error("File is not part of any config directory.")
        raise Exit(1)

    @property
    def tf_default_args(self):
        """Array of strings containing all valid config files for layer as parameters for Terraform"""
        common_config_files = [
            f"-var-file={self._guest_config_file(common_file)}"
            for common_file in self.common_config_dir.glob("*.tfvars")
        ]
        account_config_files = [
            f"-var-file={self._guest_config_file(account_file)}"
            for account_file in self.account_config_dir.glob("*.tfvars")
        ]
        return common_config_files + account_config_files

    def enable_mfa(self):
        """Enable Multi-Factor Authentication."""
        self.mfa_enabled = True

    def enable_sso(self):
        """Enable Single Sign-On Authentication."""
        self.sso_enabled = True

    def disable_authentication(self):
        """Disable all authentication."""
        self.mfa_enabled = False
        self.sso_enabled = False

    def _check_sso_token(self):
        """Check for the existence and validity of the SSO token to be used to get credentials."""

        # Adding `token` file name to this function in order to
        # meet the requirement regarding to have just one
        # token file in the sso/cache
        sso_role = self.account_conf.get("sso_role")
        token_file = self.sso_cache / sso_role

        token_files = list(self.sso_cache.glob("*"))
        if not token_files:
            logger.error("No AWS SSO token found. Please log in or configure SSO.")
            raise Exit(1)

        if token_file not in token_files:
            sso_role = "token"
            token_file = self.sso_cache / sso_role
            if token_file not in token_files:
                logger.error(
                    "No valid AWS SSO token found for current account.\n"
                    "Please log out and reconfigure SSO before proceeding."
                )
                raise Exit(1)

        entrypoint = self.entrypoint
        self.entrypoint = ""

        _, cached_token = self._exec(f"sh -c 'cat $SSO_CACHE_DIR/{sso_role}'")
        token = json.loads(cached_token)
        expiry = datetime.strptime(token.get("expiresAt"), "%Y-%m-%dT%H:%M:%SZ")
        renewal = datetime.utcnow()

        if expiry < renewal:
            logger.error("AWS SSO token has expired, please log back in.")
            raise Exit(1)

        self.entrypoint = entrypoint

    def check_for_layer_location(self):
        """Make sure the command is being ran at layer level. If not, bail."""
        if self.cwd in (self.common_config_dir, self.account_config_dir):
            logger.error("Currently in a configuration directory, no Terraform command can be run here.")
            raise Exit(1)

        if self.cwd in (self.root_dir, self.account_dir):
            logger.error(
                "Terraform commands cannot run neither in the root of the project or in"
                " the root directory of an account."
            )
            raise Exit(1)

        if not list(self.cwd.glob("*.tf")):
            logger.error("This command can only run at [bold]layer[/bold] level.")
            raise Exit(1)

    def start(self, command, *arguments):
        with AwsCredsEntryPoint(self, self.entrypoint):
            return self._start(command, *arguments)

    def start_in_layer(self, command, *arguments):
        """Run a command that can only be performed in layer level."""
        self.check_for_layer_location()

        return self.start(command, *arguments)

    def exec(self, command, *arguments):
        with AwsCredsEntryPoint(self):
            return self._exec(command, *arguments)

    # FIXME: we have a context manager for this now, remove this method later!
    def system_exec(self, command):
        """Momentarily override the container's default entrypoint. To run arbitrary commands and not only AWS CLI ones."""
        original_entrypoint = self.entrypoint
        self.entrypoint = ""
        exit_code, output = self._exec(command)

        self.entrypoint = original_entrypoint
        return exit_code, output

    def start_shell(self):
        """Launch a shell in the container."""
        if self.mfa_enabled or self.sso_enabled:
            self.check_for_layer_location()

        with AwsCredsEntryPoint(self, override_entrypoint=""):
            self._start(self.SHELL)

    def set_backend_key(self, skip_validation=False):
        # Scenarios:
        #
        # scenario    |  s3 backend set   |  s3 key set  |  skip_validation  |  result
        # 0           |  false            |  false       |  false            |  fail
        # 1           |  false            |  false       |  true             |  ok
        # 2           |  true             |  false       |  false/true       |  set the key
        # 3           |  true             |  true        |  false/true       |  read the key
        try:
            config_tf_file = self.cwd / "config.tf"
            config_tf = hcl2.loads(config_tf_file.read_text()) if config_tf_file.exists() else {}
            if (
                "terraform" in config_tf
                and "backend" in config_tf["terraform"][0]
                and "s3" in config_tf["terraform"][0]["backend"][0]
            ):
                if "key" in config_tf["terraform"][0]["backend"][0]["s3"]:
                    backend_key = config_tf["terraform"][0]["backend"][0]["s3"]["key"]
                    self._backend_key = backend_key
                else:
                    self._backend_key = f"{self.cwd.relative_to(self.root_dir).as_posix()}/terraform.tfstate".replace(
                        "/base-", "/"
                    ).replace("/tools-", "/")

                    in_container_file_path = (
                        f"{self.guest_base_path}/{config_tf_file.relative_to(self.root_dir).as_posix()}"
                    )
                    resp = self.system_exec(
                        "hcledit "
                        f"-f {in_container_file_path} -u"
                        f' attribute append terraform.backend.key "\\"{self._backend_key}\\""'
                    )
            else:
                if not skip_validation:
                    raise KeyError()
        except (KeyError, IndexError):
            logger.error(
                "[red]✘[/red] Malformed [bold]config.tf[/bold] file. Missing Terraform backend block. In some cases you may want to skip this check by using the --skip-validation flag, e.g. the first time you initialize a terraform-backend layer."
            )
            raise Exit(1)
        except Exception as e:
            logger.error("[red]✘[/red] Malformed [bold]config.tf[/bold] file. Unable to parse.")
            logger.debug(e)
            raise Exit(1)

    @property
    def backend_key(self):
        return self._backend_key

    @backend_key.setter
    def backend_key(self, backend_key):
        self._backend_key = backend_key


class TFautomvContainer(TerraformContainer):
    """Leverage Container tailored to run general commands."""

    TFAUTOMV_CLI_BINARY = "/usr/local/bin/tfautomv"

    def __init__(self, client):
        super().__init__(client)

        self.environment["TF_CLI_ARGS_init"] = " ".join(self.tf_default_args)
        self.environment["TF_CLI_ARGS_plan"] = " ".join(self.tf_default_args)

        self.entrypoint = self.TFAUTOMV_CLI_BINARY

        logger.debug(f"[bold cyan]Container configuration:[/bold cyan]\n{json.dumps(self.container_config, indent=2)}")

    def start(self, *arguments):
        with AwsCredsEntryPoint(self):
            return self._start("", *arguments)

    def start_in_layer(self, *arguments):
        """Run a command that can only be performed in layer level."""
        self.check_for_layer_location()

        return self.start(*arguments)

    def exec(self, command, *arguments):
        with AwsCredsEntryPoint(self):
            return self._exec(command, *arguments)
