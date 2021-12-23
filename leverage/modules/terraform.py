"""
    Module for interacting with the Leverage custom docker container. Allowing for
    execution of Terraform commands and interaction with the AWS CLI for infrastructure handling.
"""
import json
from pathlib import Path
from functools import wraps

import click
from click.exceptions import Exit
import dockerpty
from docker.types import Mount
from docker import DockerClient
from docker.errors import APIError

from leverage import conf
from leverage import logger
from leverage.logger import console
from leverage.logger import get_mfa_script_log_level
from leverage.path import get_working_path
from leverage.path import get_home_path
from leverage.path import get_root_path
from leverage.path import get_account_path
from leverage.path import get_global_config_path
from leverage.path import get_account_config_path
from leverage.path import NotARepositoryError


# Terraform image definitions
TERRAFORM_IMAGE = "binbash/terraform-awscli-slim"
DEFAULT_IMAGE_TAG = "1.0.9"
TERRAFORM_BINARY = "/bin/terraform"
TERRAFORM_MFA_ENTRYPOINT = "/root/scripts/aws-mfa/aws-mfa-entrypoint.sh"
WORKING_DIR = "/go/src/project"

CWD = get_working_path()
HOME = get_home_path()
try:
    ROOT = get_root_path()
    CONFIG = get_global_config_path()
    ACCOUNT = get_account_path()
    ACCOUNT_CONFIG = get_account_config_path()
except NotARepositoryError:
    ROOT = CONFIG = ACCOUNT = ACCOUNT_CONFIG = None

BACKEND_TFVARS = "/config/backend.tfvars"
COMMON_TFVARS = "/common-config/common.tfvars"
ACCOUNT_TFVARS = "/config/account.tfvars"
TF_DEFAULT_ARGS = [f"-var-file={var}"
                   for var in [BACKEND_TFVARS,
                               COMMON_TFVARS,
                               ACCOUNT_TFVARS]]


@click.group()
def terraform():
    """ Run Terraform commands in a custom containerized environment that provides extra functionality when interacting
    with your cloud provider such as handling multi factor authentication for you.
    All terraform subcommands that receive extra args will pass the given strings as is to their corresponding Terraform
    counterparts in the container. For example as in `leverage terraform apply -auto-approve` or
    `leverage terraform init -reconfigure`
    """
    if not all((ROOT, CONFIG, ACCOUNT, ACCOUNT_CONFIG)):
        logger.error("Not running in a Leverage project. Exiting.")
        raise Exit(1)


def check_directory(command):
    """ Decorator to make sure the command is run exclusively in a layer directory. """
    @wraps(command)
    def checked(*args, **kwargs):
        if CWD in (CONFIG, ACCOUNT_CONFIG):
            logger.error("Currently in a configuration directory, no Terraform command can be run here.")
            return

        if CWD in (ROOT, ACCOUNT):
            logger.error("Terraform commands cannot run neither in the root of the project or in"
                        " the root directory of an account.")
            return

        return command(*args, **kwargs)

    return checked


def ensure_image(docker_client, image, tag):
    """ Check if the required image exists, if not, pull it from the registry.

    Args:
        docker_client (docker.DockerClient): Point of communication with Docker.
        image (str): Name of the required image.
        tag (str): Tag of the required image.
    """
    found_image = docker_client.api.images(f"{image}:{tag}")

    if found_image:
        return

    logger.info("Required docker image not found.")

    stream = docker_client.api.pull(repository=image,
                                    tag=tag,
                                    stream=True,
                                    decode=True)
    logger.info(next(stream)["status"])

    imageinfo = []
    with console.status("Pulling image..."):
        for status in stream:
            status = status["status"]
            if status.startswith("Digest") or status.startswith("Status"):
                imageinfo.append(status)

    for info in imageinfo:
        logger.info(info)


def run(entrypoint=TERRAFORM_BINARY, command="", args=None, enable_mfa=True, interactive=True):
    """ Run a command on a Leverage docker container.

    Args:
        entrypoint (str, optional): Entrypoint to use in the container, overrides the one defined in the image.
            Defaults to `/bin/terraform`.
        command (str, optional): Command to run. Defaults to "".
        args (list(str)), optional): Command arguments. Defaults to None.
        enable_mfa (bool, optional): Whether to enable multi factor authentication. Defaults to True.
        interactive (bool, optional): If set to False, container will be run in the background and its output grabbed after its
            execution ends, otherwise access to the container terminal will be given. Defaults to True

    Returns:
        int, str: Container exit code and output when interactive is false, otherwise 0, None.
    """
    try:
        docker_client = DockerClient(base_url="unix://var/run/docker.sock")

    except:
        logger.error("Docker daemon doesn't seem to be responding. "
                     "Please check it is up and running correctly before re-running the command.")
        raise Exit(1)

    env = conf.load()
    logger.debug(f"[bold cyan]Env config values:[/bold cyan]\n{json.dumps(env, indent=2)}")

    project = env.get("PROJECT", False)
    if not project:
        logger.error("Project name has not been set. Exiting.")
        raise Exit(1)

    aws_credentials_directory = Path(HOME) / ".aws" / project
    if not aws_credentials_directory.exists():
        aws_credentials_directory.mkdir(parents=True)

    terraform_image_tag = env.get("TERRAFORM_IMAGE_TAG", DEFAULT_IMAGE_TAG)
    ensure_image(docker_client=docker_client,
                 image=TERRAFORM_IMAGE,
                 tag=terraform_image_tag)

    mounts = [
        Mount(target=WORKING_DIR, source=CWD, type="bind"),
        # Mount(target="/root/.ssh", source=f"{HOME}/.ssh", type="bind"), # SSH keys for Ansible
        # Mount(target="/etc/gitconfig", source=f"{HOME}/.gitconfig", type="bind"), # Git user configuration
        Mount(target=f"/root/tmp/{project}", source=f"{HOME}/.aws/{project}", type="bind")
    ]
    if Path(str(CONFIG)).exists() and Path(str(ACCOUNT_CONFIG)).exists():
        mounts.extend([
            Mount(target="/common-config", source=CONFIG, type="bind"),
            Mount(target="/config", source=ACCOUNT_CONFIG, type="bind")
        ])

    environment = {
        "AWS_SHARED_CREDENTIALS_FILE": f"/root/.aws/{project}/credentials",
        "AWS_CONFIG_FILE": f"/root/.aws/{project}/config",
        "BACKEND_CONFIG_FILE": BACKEND_TFVARS,
        "COMMON_CONFIG_FILE": COMMON_TFVARS,
        "SRC_AWS_CONFIG_FILE": f"/root/tmp/{project}/config",
        "SRC_AWS_SHARED_CREDENTIALS_FILE": f"/root/tmp/{project}/credentials",
        "AWS_CACHE_DIR": f"/root/tmp/{project}/cache",
        "MFA_SCRIPT_LOG_LEVEL": get_mfa_script_log_level()
    }

    if entrypoint == TERRAFORM_BINARY:
        enable_mfa = enable_mfa and env.get("MFA_ENABLED") == "true"

    if enable_mfa:
        # A layer is a directory with .tf files inside
        if not list(Path(CWD).glob("*.tf")):
            logger.error("This command can only run at [bold]layer[/bold] level.")
            raise Exit(1)

        if command or entrypoint != TERRAFORM_BINARY:
            entrypoint = f"{TERRAFORM_MFA_ENTRYPOINT} -- {entrypoint}"
        else:
            entrypoint = TERRAFORM_MFA_ENTRYPOINT

    else:
        environment.update({
            "AWS_CONFIG_FILE": f"/root/tmp/{project}/config",
            "AWS_SHARED_CREDENTIALS_FILE": f"/root/tmp/{project}/credentials"
        })

    args = [] if args is None else args
    command = " ".join([command] + args)

    host_config = docker_client.api.create_host_config(mounts=mounts,
                                                       security_opt=["label:disable"])
    container_params = {
        "image": f"{TERRAFORM_IMAGE}:{terraform_image_tag}",
        "environment": environment,
        "entrypoint": entrypoint,
        "working_dir": WORKING_DIR,
        "host_config": host_config,
        "command": command
    }
    try:
        container = docker_client.api.create_container(**container_params, stdin_open=True, tty=True)

    except APIError as exc:
        logger.exception("Error creating container:", exc_info=exc)
        raise Exit(1)

    logger.debug(f"[bold cyan]Container parameters:[/bold cyan]\n{json.dumps(container_params, indent=2)}")

    container_output = None
    container_exit_code = 0
    try:
        if interactive:
            dockerpty.start(client=docker_client.api,
                            container=container)
            container_exit_code = docker_client.api.inspect_container(container)["State"]["ExitCode"]
        else:
            docker_client.api.start(container)
            container_exit_code = docker_client.api.wait(container)["StatusCode"]
            container_output = docker_client.api.logs(container).decode("utf-8")

    except APIError as exc:
        logger.exception("Error during container execution:", exc_info=exc)

    finally:
        docker_client.api.stop(container)
        docker_client.api.remove_container(container)

    return container_exit_code, container_output


def awscli(command):
    """ Utility function to run AWS cli commands in a simple and readable line from within leverage.

    Args:
        commands (str | list): Command or list Full command to run.

    Returns:
        int, str: Command's exit code and output.
    """
    return run(entrypoint="/usr/bin/aws",
               command=command,
               enable_mfa=False,
               interactive=False)


CONTEXT_SETTINGS = {"ignore_unknown_options": True}


@terraform.command(context_settings=CONTEXT_SETTINGS)
@click.option("--no-backend",
              is_flag=True)
@click.argument("args", nargs=-1)
@check_directory
def init(no_backend, args):
    """ Initialize this layer. """
    backend_config = ["-backend=false" if no_backend else f"-backend-config={BACKEND_TFVARS}"]
    exit_code, _ = run(command="init", args=backend_config + list(args))

    if exit_code:
        raise Exit(exit_code)


@terraform.command(context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1)
@check_directory
def plan(args):
    """ Generate an execution plan for this layer. """
    exit_code, _ = run(command="plan", args=TF_DEFAULT_ARGS + list(args))

    if exit_code:
        raise Exit(exit_code)


@terraform.command(context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1)
@check_directory
def apply(args):
    """ Build or change the infrastructure in this layer. """
    exit_code, _ = run(command="apply", args=TF_DEFAULT_ARGS + list(args))

    if exit_code:
        raise Exit(exit_code)


@terraform.command(context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1)
@check_directory
def output(args):
    """ Show all output variables of this layer. """
    run(command="output", args=list(args))


@terraform.command(context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1)
@check_directory
def destroy(args):
    """ Destroy infrastructure in this layer. """
    run(command="destroy", args=TF_DEFAULT_ARGS + list(args))


@terraform.command()
def version():
    """ Print version. """
    run(command="version", enable_mfa=False)


@terraform.command()
@click.option("--mfa",
              is_flag=True,
              default=False,
              help="Enable Multi Factor Authentication upon launching shell.")
def shell(mfa):
    """ Open a shell into the Terraform container in this layer. """
    runshell = check_directory(run) if mfa else run
    runshell(entrypoint="/bin/sh", enable_mfa=mfa)


@terraform.command("format")
@click.option("--check",
              is_flag=True,
              help="Only perform format checking, do not rewrite the files.")
def _format(check):
    """ Check if all files meet the canonical format and rewrite them accordingly. """
    arguments = ["-recursive"]
    if check:
        arguments.extend(["-check", WORKING_DIR])
    run(command="fmt", args=arguments, enable_mfa=False)


@terraform.command()
def validate():
    """ Validate code of the current directory. Previous initialization might be needed. """
    run(command="validate", enable_mfa=False)


@terraform.command("import")
@click.argument("address")
@click.argument("_id", metavar="ID")
@check_directory
def _import(address, _id):
    """ Import a resource. """
    exit_code, _ = run(command="import", args=TF_DEFAULT_ARGS + [address, _id])

    if exit_code:
        raise Exit(exit_code)


@terraform.command(context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1)
def aws(args):
    """ Run a command in AWS cli. """
    run(entrypoint="/usr/bin/aws", args=list(args), enable_mfa=False)
