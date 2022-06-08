import json
from pathlib import Path
from datetime import datetime
from datetime import timedelta

import hcl2
from click.exceptions import Exit
import dockerpty
from docker import DockerClient
from docker.errors import APIError
from docker.types import Mount

from leverage import logger
from leverage.logger import console
from leverage.logger import get_script_log_level
from leverage.path import get_root_path
from leverage.path import get_account_path
from leverage.path import get_global_config_path
from leverage.path import get_account_config_path
from leverage.path import NotARepositoryError
from leverage.conf import load as load_env


def get_docker_client():
    """ Attempt to get a Docker client from the environment configuration. Halt application otherwise.

    Raises:
        Exit: If communication to Docker server could not be established.

    Returns:
        docker.DockerClient: Client for Docker daemon.
    """
    try:
        docker_client = DockerClient.from_env()
        docker_client.ping()

    except:
        logger.error("Docker daemon doesn't seem to be responding. "
                     "Please check it is up and running correctly before re-running the command.")
        raise Exit(1)

    return docker_client


class LeverageContainer:
    """ Basic Leverage Container. Holds the minimum information required to run the Docker image that Leverage uses
    to perform its operations. Commands can be issued as interactive via `start` for when live output or user input is desired
    or the can be simply executed via `exec` to run silently and retrieve the command output.

    NOTE: An aggregation approach to this design should be considered instead of the current inheritance approach.
    """
    LEVERAGE_IMAGE = "binbash/terraform-awscli-slim"

    SSO_LOGIN_URL = "https://device.sso.{region}.amazonaws.com"

    COMMON_TFVARS = "common.tfvars"
    ACCOUNT_TFVARS = "account.tfvars"
    BACKEND_TFVARS = "backend.tfvars"

    def __init__(self, client):
        """ Project related paths are determined and stored. Project configuration is loaded.

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
            logger.error("No docker image tag defined.\n"
                         "Please set `TERRAFORM_IMAGE_TAG` variable before running a Leverage command.")
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

        self.host_config = self.client.api.create_host_config(
            security_opt=["label:disable"],
            mounts=[]
        )
        self.container_config = {
            "image": f"{self.image}:{self.image_tag}",
            "command": "",
            "stdin_open": True,
            "environment": {},
            "entrypoint": "",
            "working_dir": f"{self.guest_base_path}/{self.cwd.relative_to(self.root_dir).as_posix()}",
            "host_config": self.host_config
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

    def ensure_image(self):
        """ Make sure the required Docker image is available in the system. If not, pull it from registry. """
        found_image = self.client.api.images(f"{self.image}:{self.image_tag}")
        if found_image:
            return

        logger.info("Required Docker image not found.")

        stream = self.client.api.pull(repository=self.image, tag=self.image_tag, stream=True, decode=True)
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
        """ Create the container that will run the command.

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
        """ Apply the given run function to the given container, return its outputs and handle container cleanup.

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

    def _start(self, command="/bin/sh", *args):
        """ Create an interactive container, and run command with the given arguments.

        Args:
            command (str, optional): Command to run. Defaults to "/bin/sh".

        Returns:
            int: Execution exit code.
        """
        container = self._create_container(True, command, *args)

        def run_func(client, container):
            dockerpty.start(client=client.api, container=container)
            return client.api.inspect_container(container)["State"]["ExitCode"]

        return self._run(container, run_func)

    def start(self, command="/bin/sh", *arguments):
        """ Run command with the given arguments in an interactive container.

        Args:
            command (str, optional): Command. Defaults to "/bin/sh".

        Returns:
            int: Execution exit code.
        """
        return self._start(command, *arguments)

    def _exec(self, command="", *args):
        """ Create a non interactive container and execute command with the given arguments.

        Args:
            command (str, optional): Command. Defaults to "".

        Returns:
            int, str: Execution exit code and output.
        """
        container = self._create_container(False, command, *args)

        def run_func(client, container):
            client.api.start(container)
            exit_code = client.api.wait(container)["StatusCode"]
            output = client.api.logs(container).decode("utf-8")
            return exit_code, output

        return self._run(container, run_func)

    def exec(self, command="", *arguments):
        """ Execute command with the given arguments in a container.

        Args:
            command (str, optional): Command. Defaults to "".

        Returns:
            int, str: Execution exit code and output/
        """
        return self._exec(command, *arguments)


class AWSCLIContainer(LeverageContainer):
    """ Leverage Container specially tailored to run AWS CLI commands. """
    AWS_CLI_BINARY = "/usr/local/bin/aws"

    AWS_SSO_LOGIN_SCRIPT = "/root/scripts/aws-sso/aws-sso-login.sh"
    AWS_SSO_LOGOUT_SCRIPT = "/root/scripts/aws-sso/aws-sso-logout.sh"
    AWS_SSO_CONFIGURE_SCRIPT = "/root/scripts/aws-sso/aws-sso-configure.sh"

    def __init__(self, client):
        super().__init__(client)

        self.environment = {
            "COMMON_CONFIG_FILE": self.common_tfvars,
            "ACCOUNT_CONFIG_FILE": self.account_tfvars,
            "BACKEND_CONFIG_FILE": self.backend_tfvars,
            "AWS_SHARED_CREDENTIALS_FILE": f"{self.guest_aws_credentials_dir}/credentials",
            "AWS_CONFIG_FILE": f"{self.guest_aws_credentials_dir}/config",
            "SSO_CACHE_DIR": f"{self.guest_aws_credentials_dir}/sso/cache",
            "SCRIPT_LOG_LEVEL": get_script_log_level()
        }
        self.entrypoint = self.AWS_CLI_BINARY
        self.mounts = [
            Mount(source=self.root_dir.as_posix(), target=self.guest_base_path, type="bind"),
            Mount(source=self.host_aws_credentials_dir.as_posix(), target=self.guest_aws_credentials_dir, type="bind")
        ]

        logger.debug(f"[bold cyan]Container configuration:[/bold cyan]\n{json.dumps(self.container_config, indent=2)}")


    def start(self, command, profile=""):
        args = [] if not profile else ["--profile", profile]
        return self._start(command, *args)

    def system_start(self, command):
        """ Momentarily override the container's default entrypoint. To run arbitrary commands and not only AWS CLI ones. """
        self.entrypoint = ""
        exit_code = self._start(command)
        self.entrypoint = self.AWS_CLI_BINARY
        return exit_code

    def exec(self, command, profile=""):
        args = [] if not profile else ["--profile", profile]
        return self._exec(command, *args)

    def system_exec(self, command):
        """ Momentarily override the container's default entrypoint. To run arbitrary commands and not only AWS CLI ones. """
        self.entrypoint = ""
        exit_code, output = self._exec(command)

        self.entrypoint = self.AWS_CLI_BINARY
        return exit_code, output


class TerraformContainer(LeverageContainer):
    """ Leverage container specifically tailored to run Terraform commands.
    It handles authentication and some checks regarding where the command is being executed. """
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
        self.mfa_enabled = self.env_conf.get("MFA_ENABLED", "false") == "true" # TODO: Convert values to bool upon loading

        self.environment = {
            "COMMON_CONFIG_FILE": self.common_tfvars,
            "ACCOUNT_CONFIG_FILE": self.account_tfvars,
            "BACKEND_CONFIG_FILE": self.backend_tfvars,
            "AWS_SHARED_CREDENTIALS_FILE": f"{self.guest_aws_credentials_dir}/credentials",
            "AWS_CONFIG_FILE": f"{self.guest_aws_credentials_dir}/config",
            "SRC_AWS_SHARED_CREDENTIALS_FILE": f"{self.guest_aws_credentials_dir}/credentials", # Legacy?
            "SRC_AWS_CONFIG_FILE": f"{self.guest_aws_credentials_dir}/config", # Legacy?
            "AWS_CACHE_DIR": f"{self.guest_aws_credentials_dir}/cache",
            "SSO_CACHE_DIR": f"{self.guest_aws_credentials_dir}/sso/cache",
            "SCRIPT_LOG_LEVEL": get_script_log_level(),
            "MFA_SCRIPT_LOG_LEVEL": get_script_log_level() # Legacy
        }
        self.entrypoint = self.TF_BINARY
        self.mounts = [
            Mount(source=self.root_dir.as_posix(), target=self.guest_base_path, type="bind"),
            Mount(source=self.host_aws_credentials_dir.as_posix(), target=self.guest_aws_credentials_dir, type="bind"),
            Mount(source=(self.home / ".ssh").as_posix(), target="/root/.ssh", type="bind"),
            Mount(source=(self.home / ".gitconfig").as_posix(), target="/etc/gitconfig", type="bind")
        ]

        logger.debug(f"[bold cyan]Container configuration:[/bold cyan]\n{json.dumps(self.container_config, indent=2)}")

    def _guest_config_file(self, file):
        """ Map config file in host to location in guest.

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
        """ Array of strings containing all valid config files for layer as parameters for Terraform """
        common_config_files = [f"-var-file={self._guest_config_file(common_file)}"
                               for common_file in self.common_config_dir.glob("*.tfvars")]
        account_config_files = [f"-var-file={self._guest_config_file(account_file)}"
                                for account_file in self.account_config_dir.glob("*.tfvars")]
        return common_config_files + account_config_files

    def enable_mfa(self):
        """ Enable Multi-Factor Authentication. """
        self.mfa_enabled = True

    def enable_sso(self):
        """ Enable Single Sign-On Authentication. """
        self.sso_enabled = True

    def disable_authentication(self):
        """ Disable all authentication. """
        self.mfa_enabled = False
        self.sso_enabled = False

    def _check_sso_token(self):
        """ Check for the existence and validity of the SSO token to be used to get credentials. """
        sso_role = self.account_conf.get("sso_role")
        token_file = self.sso_cache / sso_role

        token_files = list(self.sso_cache.glob("*"))
        if not token_files:
            logger.error("No AWS SSO token found. Please log in or configure SSO.")
            raise Exit(1)

        if token_file not in token_files:
            logger.error("No valid AWS SSO token found for current account.\n"
                         "Please log out and reconfigure SSO before proceeding.")
            raise Exit(1)

        entrypoint = self.entrypoint
        self.entrypoint = ""

        _, cached_token = self._exec(f"sh -c 'cat $SSO_CACHE_DIR/{sso_role}'")
        token = json.loads(cached_token)
        expiry = datetime.strptime(token.get("expiresAt"), "%Y-%m-%dT%H:%M:%SZ")
        renewal = datetime.now() + timedelta(hours=7)

        if expiry < renewal:
            logger.error("AWS SSO token has expired, please log back in.")
            raise Exit(1)

        self.entrypoint = entrypoint

    def _prepare_container(self):
        """ Adjust entrypoint and environment variables for when SSO or MFA are used.
        Note that SSO takes precedence over MFA when both are active. """
        if self.sso_enabled:
            self._check_sso_token()

            self.entrypoint = f"{self.TF_SSO_ENTRYPOINT} -- {self.entrypoint}"

        elif self.mfa_enabled:
            self.entrypoint = f"{self.TF_MFA_ENTRYPOINT} -- {self.entrypoint}"

            self.environment.update({
                "AWS_SHARED_CREDENTIALS_FILE": self.environment.get("AWS_SHARED_CREDENTIALS_FILE").replace("tmp", ".aws"),
                "AWS_CONFIG_FILE": self.environment.get("AWS_CONFIG_FILE").replace("tmp", ".aws"),
            })

        logger.debug(f"[bold cyan]Running with entrypoint:[/bold cyan] {self.entrypoint}")

    def check_for_layer_location(self):
        """ Make sure the command is being ran at layer level. If not, bail. """
        if self.cwd in (self.common_config_dir, self.account_config_dir):
            logger.error("Currently in a configuration directory, no Terraform command can be run here.")
            raise Exit(1)

        if self.cwd in (self.root_dir, self.account_dir):
            logger.error("Terraform commands cannot run neither in the root of the project or in"
                         " the root directory of an account.")
            raise Exit(1)

        if not list(self.cwd.glob("*.tf")):
            logger.error("This command can only run at [bold]layer[/bold] level.")
            raise Exit(1)

    def start(self, command, *arguments):
        self._prepare_container()

        return self._start(command, *arguments)

    def start_in_layer(self, command, *arguments):
        """ Run a command that can only be performed in layer level. """
        self.check_for_layer_location()

        return self.start(command, *arguments)

    def exec(self, command, *arguments):
        self._prepare_container()

        return self._exec(command, *arguments)

    def start_shell(self):
        """ Launch a shell in the container. """
        if self.mfa_enabled or self.sso_enabled:
            self.check_for_layer_location()

        self.entrypoint = ""
        self._prepare_container()
        self._start()
