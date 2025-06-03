import json
import os
import re
import webbrowser
from io import BytesIO
from datetime import datetime
from time import sleep

import hcl2
from click.exceptions import Exit
import dockerpty
from configupdater import ConfigUpdater
from docker import DockerClient
from docker.errors import APIError
from docker.types import Mount
from typing import Tuple

from leverage import logger
from leverage._utils import AwsCredsEntryPoint, CustomEntryPoint, ExitError, ContainerSession
from leverage.modules.auth import refresh_layer_credentials
from leverage.logger import raw_logger
from leverage.logger import get_script_log_level
from leverage.path import PathsHandler
from leverage.conf import load as load_env

REGION = (
    r"(.*)"  # project folder
    # start region
    r"(global|(?:[a-z]{2}-(?:gov-)?"
    r"(?:central|north|south|east|west|northeast|northwest|southeast|southwest|secret|topsecret)-[1-4]))"
    # end region
    r"(.*)"  # layer
)


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
    SHELL = "/bin/bash"
    CONTAINER_USER = "leverage"

    def __init__(self, client, mounts: tuple = None, env_vars: dict = None):
        """Project related paths are determined and stored. Project configuration is loaded.

        Args:
            client (docker.DockerClient): Client to interact with Docker daemon.
        """
        self.client = client
        # Load configs
        self.env_conf = load_env()

        self.paths = PathsHandler(self.env_conf, self.CONTAINER_USER)
        self.project = self.paths.project

        # Set image to use
        self.image = self.env_conf.get("TERRAFORM_IMAGE", self.LEVERAGE_IMAGE)
        self.image_tag = self.env_conf.get("TERRAFORM_IMAGE_TAG")
        if not self.image_tag:
            logger.error(
                "No docker image tag defined.\n"
                "Please set `TERRAFORM_IMAGE_TAG` variable in the project's [bold]build.env[/bold] file before running a Leverage command."
            )
            raise Exit(1)

        mounts = [Mount(source=source, target=target, type="bind") for source, target in mounts] if mounts else []
        self.host_config = self.client.api.create_host_config(security_opt=["label=disable"], mounts=mounts)
        self.container_config = {
            "image": f"{self.image}:{self.local_image_tag}",
            "command": "",
            "stdin_open": True,
            "environment": env_vars or {},
            "entrypoint": "",
            "working_dir": f"{self.paths.guest_base_path}/{self.paths.cwd.relative_to(self.paths.root_dir).as_posix()}",
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
    def region(self):
        """
        Return the region of the layer.
        """
        if matches := re.match(REGION, self.paths.cwd.as_posix()):
            # the region (group 1) is between the projects folders (group 0) and the layers (group 2)
            return matches.groups()[1]

        raise ExitError(1, f"No valid region could be found at: {self.paths.cwd.as_posix()}")

    @property
    def local_image_tag(self):
        return f"{self.image_tag}-{os.getgid()}-{os.getuid()}"

    @property
    def local_image(self) -> BytesIO:
        """Return the local image that will be built, as a file-like object."""
        return BytesIO(
            """
            ARG IMAGE_TAG
            FROM binbash/leverage-toolbox:$IMAGE_TAG

            ARG UNAME
            ARG UID
            ARG GID
            RUN groupadd -g $GID -o $UNAME
            RUN useradd -m -u $UID -g $GID -o -s /bin/bash $UNAME
            RUN chown -R $UID:$GID /home/leverage
            USER $UNAME
            """.encode(
                "utf-8"
            )
        )

    def ensure_image(self):
        """
        Make sure the required local Docker image is available in the system. If not, build it.
        If the image already exists, re-build it so changes in the arguments can take effect.
        """
        logger.info(f"Checking for local docker image, tag: {self.local_image_tag}...")
        image_name = f"{self.image}:{self.local_image_tag}"

        # check first is our image is already available locally
        found_image = self.client.api.images(f"{self.image}:{self.local_image_tag}")
        if found_image:
            logger.info("[green]✔ OK[/green]\n")
            return

        logger.info(f"Image not found, building it...")
        build_args = {
            "IMAGE_TAG": self.image_tag,
            "UNAME": self.CONTAINER_USER,
            "GID": str(os.getgid()),
            "UID": str(os.getuid()),
        }

        stream = self.client.api.build(
            fileobj=self.local_image,
            tag=image_name,
            pull=True,
            buildargs=build_args,
            decode=True,
        )

        for line in stream:
            if "stream" in line and line["stream"].startswith("Successfully built"):
                logger.info("[green]✔ OK[/green]\n")
            elif "errorDetail" in line:
                raise ExitError(1, f"Failed building local image: {line['errorDetail']}")

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


class SSOContainer(LeverageContainer):
    # SSO scripts
    AWS_SSO_LOGIN_SCRIPT = "/home/leverage/scripts/aws-sso/aws-sso-login.sh"
    AWS_SSO_LOGOUT_SCRIPT = "/home/leverage/scripts/aws-sso/aws-sso-logout.sh"

    # SSO constants
    AWS_SSO_LOGIN_URL = "{sso_url}/#/device?user_code={user_code}"
    AWS_SSO_CODE_WAIT_SECONDS = 2
    AWS_SSO_CODE_ATTEMPTS = 10
    FALLBACK_LINK_MSG = "Opening the browser... if it fails, open this link in your browser:\n{link}"

    def get_sso_access_token(self):
        with open(self.paths.sso_token_file) as token_file:
            return json.loads(token_file.read())["accessToken"]

    @property
    def sso_region_from_main_profile(self):
        """
        Same than AWSCLIContainer.get_sso_region but without using a container.
        """
        conf = ConfigUpdater()
        conf.read(self.paths.host_aws_profiles_file)
        return conf.get(f"profile {self.project}-sso", "sso_region").value

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
            else:
                logger.debug(logs)
            sleep(self.AWS_SSO_CODE_WAIT_SECONDS)

        raise ExitError(1, "Get SSO code timed-out")

    def get_sso_region(self):
        # TODO: what about using the .region property we have now? that takes the value from the path of the layer
        _, region = self.exec(f"configure get sso_region --profile {self.project}-sso")
        return region

    def sso_login(self) -> int:
        region = self.get_sso_region()

        with CustomEntryPoint(self, "sh -c"):
            container = self._create_container(False, command=self.AWS_SSO_LOGIN_SCRIPT)

        with ContainerSession(self.client, container):
            # once inside this block, the SSO_LOGIN_SCRIPT is being executed in the "background"
            # now let's grab the user code from the logs
            user_code = self.get_sso_code(container)
            # with the user code, we can now autocomplete the url
            link = self.AWS_SSO_LOGIN_URL.format(sso_url=self.paths.common_conf["sso_start_url"], user_code=user_code)
            webbrowser.open_new_tab(link)
            # The SSO code is only valid once: if the browser was able to open it, the fallback link will be invalid
            logger.info(self.FALLBACK_LINK_MSG.format(link=link))
            # now let's wait until the command locking the container resolve itself:
            # aws sso login will wait for the user code
            # once submitted to the browser, the authentication finish and the lock is released
            exit_code = self.client.api.wait(container)["StatusCode"]
            raw_logger.info(self.docker_logs(container))

        return exit_code


class AWSCLIContainer(SSOContainer):
    """Leverage Container specially tailored to run AWS CLI commands."""

    AWS_CLI_BINARY = "/usr/local/bin/aws"

    def __init__(self, client):
        super().__init__(client)

        self.environment = {
            "COMMON_CONFIG_FILE": self.paths.common_tfvars,
            "ACCOUNT_CONFIG_FILE": self.paths.account_tfvars,
            "BACKEND_CONFIG_FILE": self.paths.backend_tfvars,
            "AWS_SHARED_CREDENTIALS_FILE": f"{self.paths.guest_aws_credentials_dir}/credentials",
            "AWS_CONFIG_FILE": f"{self.paths.guest_aws_credentials_dir}/config",
            "SSO_CACHE_DIR": f"{self.paths.guest_aws_credentials_dir}/sso/cache",
            "SCRIPT_LOG_LEVEL": get_script_log_level(),
        }
        self.entrypoint = self.AWS_CLI_BINARY
        self.mounts = [
            Mount(source=self.paths.root_dir.as_posix(), target=self.paths.guest_base_path, type="bind"),
            Mount(
                source=self.paths.host_aws_credentials_dir.as_posix(),
                target=self.paths.guest_aws_credentials_dir,
                type="bind",
            ),
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


class TerraformContainer(SSOContainer):
    """Leverage container specifically tailored to run Terraform commands.
    It handles authentication and some checks regarding where the command is being executed."""

    TF_BINARY = "/bin/terraform"

    TF_MFA_ENTRYPOINT = "/home/leverage/scripts/aws-mfa/aws-mfa-entrypoint.sh"

    def __init__(self, client, mounts=None, env_vars=None):
        super().__init__(client, mounts=mounts, env_vars=env_vars)

        self.paths.assert_running_leverage_project()

        # Set authentication methods
        self.sso_enabled = self.paths.common_conf.get("sso_enabled", False)
        self.mfa_enabled = (
            self.env_conf.get("MFA_ENABLED", "false") == "true"
        )  # TODO: Convert values to bool upon loading

        # SSH AGENT
        SSH_AUTH_SOCK = os.getenv("SSH_AUTH_SOCK")

        # make sure .gitconfig exists before mounting it
        self.paths.host_git_config_file.touch(exist_ok=True)

        self.environment.update(
            {
                "COMMON_CONFIG_FILE": self.paths.common_tfvars,
                "ACCOUNT_CONFIG_FILE": self.paths.account_tfvars,
                "BACKEND_CONFIG_FILE": self.paths.backend_tfvars,
                "AWS_SHARED_CREDENTIALS_FILE": f"{self.paths.guest_aws_credentials_dir}/credentials",
                "AWS_CONFIG_FILE": f"{self.paths.guest_aws_credentials_dir}/config",
                "SRC_AWS_SHARED_CREDENTIALS_FILE": f"{self.paths.guest_aws_credentials_dir}/credentials",  # Legacy?
                "SRC_AWS_CONFIG_FILE": f"{self.paths.guest_aws_credentials_dir}/config",  # Legacy?
                "AWS_CACHE_DIR": f"{self.paths.guest_aws_credentials_dir}/cache",
                "SSO_CACHE_DIR": f"{self.paths.guest_aws_credentials_dir}/sso/cache",
                "SCRIPT_LOG_LEVEL": get_script_log_level(),
                "MFA_SCRIPT_LOG_LEVEL": get_script_log_level(),  # Legacy
                "SSH_AUTH_SOCK": "" if SSH_AUTH_SOCK is None else "/ssh-agent",
            }
        )
        self.entrypoint = self.TF_BINARY
        extra_mounts = [
            Mount(source=self.paths.root_dir.as_posix(), target=self.paths.guest_base_path, type="bind"),
            Mount(
                source=self.paths.host_aws_credentials_dir.as_posix(),
                target=self.paths.guest_aws_credentials_dir,
                type="bind",
            ),
            Mount(source=self.paths.host_git_config_file.as_posix(), target="/etc/gitconfig", type="bind"),
        ]
        self.mounts.extend(extra_mounts)
        # if you have set the tf plugin cache locally
        if self.paths.tf_cache_dir:
            # then mount it too into the container
            self.environment["TF_PLUGIN_CACHE_DIR"] = self.paths.tf_cache_dir
            # given that terraform use symlinks to point from the .terraform folder into the plugin folder
            # we need to use the same directory inside the container
            # otherwise symlinks will be broken once outside the container
            # which will break terraform usage outside Leverage
            self.mounts.append(Mount(source=self.paths.tf_cache_dir, target=self.paths.tf_cache_dir, type="bind"))
        if SSH_AUTH_SOCK is not None:
            self.mounts.append(Mount(source=SSH_AUTH_SOCK, target="/ssh-agent", type="bind"))

        self._backend_key = None

        logger.debug(f"[bold cyan]Container configuration:[/bold cyan]\n{json.dumps(self.container_config, indent=2)}")

    def auth_method(self) -> str:
        """
        Return the expected auth method based on the SSO or MFA flags.

        In the case of MFA, we also need to tweak some env variables for AWS credentials.
        Once you are done with authentication, remember to revert the env var changes.
        """
        if self.sso_enabled:
            self._check_sso_token()
            # sso credentials needs to be refreshed right before we execute our command on the container
            refresh_layer_credentials(self)
        elif self.mfa_enabled:
            self.environment.update(
                {
                    "AWS_SHARED_CREDENTIALS_FILE": self.environment["AWS_SHARED_CREDENTIALS_FILE"].replace(
                        "tmp", ".aws"
                    ),
                    "AWS_CONFIG_FILE": self.environment["AWS_CONFIG_FILE"].replace("tmp", ".aws"),
                }
            )
            return f"{self.TF_MFA_ENTRYPOINT} -- "

        return ""

    @property
    def tf_default_args(self):
        """Array of strings containing all valid config files for layer as parameters for Terraform"""
        common_config_files = [
            f"-var-file={self.paths.guest_config_file(common_file)}"
            for common_file in self.paths.common_config_dir.glob("*.tfvars")
        ]
        account_config_files = [
            f"-var-file={self.paths.guest_config_file(account_file)}"
            for account_file in self.paths.account_config_dir.glob("*.tfvars")
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
        sso_role = self.paths.account_conf.get("sso_role")
        token_file = self.paths.sso_cache / sso_role

        token_files = list(self.paths.sso_cache.glob("*"))
        if not token_files:
            logger.error("No AWS SSO token found. Please log in or configure SSO.")
            raise Exit(1)

        if token_file not in token_files:
            sso_role = "token"
            token_file = self.paths.sso_cache / sso_role
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
            logger.error(
                "AWS SSO token has expired, please log back in by running [bold]leverage aws sso login[/bold]"
                " to refresh your credentials before re-running the last command."
            )
            raise Exit(1)

        self.entrypoint = entrypoint

    def refresh_credentials(self):
        with AwsCredsEntryPoint(self, override_entrypoint=""):
            if exit_code := self._start('echo "Done."'):
                return exit_code

    def start(self, command, *arguments):
        with AwsCredsEntryPoint(self, self.entrypoint):
            return self._start(command, *arguments)

    def start_in_layer(self, command, *arguments):
        """Run a command that can only be performed in layer level."""
        self.paths.check_for_layer_location()

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
            self.paths.check_for_layer_location()

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
            config_tf_file = self.paths.cwd / "config.tf"
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
                    self._backend_key = (
                        f"{self.paths.cwd.relative_to(self.paths.root_dir).as_posix()}/terraform.tfstate".replace(
                            "/base-", "/"
                        ).replace("/tools-", "/")
                    )

                    in_container_file_path = (
                        f"{self.paths.guest_base_path}/{config_tf_file.relative_to(self.paths.root_dir).as_posix()}"
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
        self.paths.check_for_layer_location()

        return self.start(*arguments)

    def exec(self, command, *arguments):
        with AwsCredsEntryPoint(self):
            return self._exec(command, *arguments)
