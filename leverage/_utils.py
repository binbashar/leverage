"""
    General use utilities.
"""
import io
import os
import tarfile
from pathlib import Path
from subprocess import run
from subprocess import PIPE

from click.exceptions import Exit
from configupdater import ConfigUpdater
from docker import DockerClient
from docker.models.containers import Container

from leverage import logger
from leverage.logger import raw_logger


def clean_exception_traceback(exception):
    """Delete special local variables from all frames of an exception's traceback
    as to avoid polluting the output when displaying it.

    Args:
        exception (Exception): The exception which traceback needs to be cleaned.

    Return:
        Exception: The exception with a clean traceback.
    """
    locals_to_delete = [
        "__builtins__",
        "__cached__",
        "__doc__",
        "__file__",
        "__loader__",
        "__name__",
        "__package__",
        "__spec__",
    ]

    traceback = exception.__traceback__

    while traceback is not None:
        frame = traceback.tb_frame
        for key in locals_to_delete:
            try:
                del frame.f_locals[key]
            except KeyError:
                pass

        traceback = traceback.tb_next

    return exception


def git(command):
    """Run the given git command.

    Args:
        command (str): Complete git command with or without the binary name.
    """
    command = command.split()
    command = ["git"] + command if command[0] != "git" else command

    run(command, stdout=PIPE, stderr=PIPE, check=True)


def chain_commands(commands: list, chain: str = " && ") -> str:
    return f'bash -c "{chain.join(commands)}"'


class CustomEntryPoint:
    """
    Set a custom entrypoint on the container while entering the context.
    Once outside, return it to its original value.
    """

    def __init__(self, container, entrypoint):
        self.container = container
        self.old_entrypoint = container.entrypoint
        self.new_entrypoint = entrypoint

    def __enter__(self):
        self.container.entrypoint = self.new_entrypoint

    def __exit__(self, *args, **kwargs):
        self.container.entrypoint = self.old_entrypoint


class AwsCredsEntryPoint(CustomEntryPoint):
    """
    Fetching AWS credentials by setting the SSO/MFA entrypoints.
    """

    def __init__(self, container, override_entrypoint=None):
        auth_method = container.auth_method()

        new_entrypoint = f"{auth_method}{container.entrypoint if override_entrypoint is None else override_entrypoint}"
        super(AwsCredsEntryPoint, self).__init__(container, entrypoint=new_entrypoint)

    def __exit__(self, *args, **kwargs):
        super(AwsCredsEntryPoint, self).__exit__(*args, **kwargs)
        if self.container.mfa_enabled:
            self.container.environment.update(
                {
                    "AWS_SHARED_CREDENTIALS_FILE": self.container.environment["AWS_SHARED_CREDENTIALS_FILE"].replace(
                        ".aws", "tmp"
                    ),
                    "AWS_CONFIG_FILE": self.container.environment["AWS_CONFIG_FILE"].replace(".aws", "tmp"),
                }
            )
        # now return file ownership on the aws credentials files
        self.container.change_file_ownership(self.container.paths.guest_aws_credentials_dir)


class AwsCredsContainer:
    """
    Fetching AWS credentials by setting the SSO/MFA entrypoints on a living container.
    This flow runs a command on a living container before any other command, leaving your AWS credentials ready
    for authentication.

    In the case of MFA, the env var tweaks (that happens at .auth_method()) must stay until the end of the block
    given the container is reused for more commands.
    """

    def __init__(self, container: Container, tf_container):
        self.container = container
        self.tf_container = tf_container

    def __enter__(self):
        auth_method = self.tf_container.auth_method()
        if not auth_method:
            return

        exit_code, output = self.container.exec_run(auth_method, environment=self.tf_container.environment)
        raw_logger.info(output.decode("utf-8"))

    def __exit__(self, *args, **kwargs):
        # now return file ownership on the aws credentials files
        self.tf_container.change_file_ownership(self.tf_container.paths.guest_aws_credentials_dir)


class ExitError(Exit):
    """
    Raise an Exit exception but also print an error description.
    """

    def __init__(self, exit_code: int, error_description: str):
        logger.error(error_description)
        super(ExitError, self).__init__(exit_code)


class ContainerSession:
    """
    Handle the start/stop cycle of a container.
    Useful when you need to keep your container alive to share context between multiple commands.
    """

    def __init__(self, docker_client: DockerClient, container_data):
        self.docker_client = docker_client
        self.container_data = container_data

    def __enter__(self) -> Container:
        self.docker_client.api.start(self.container_data)
        return self.docker_client.containers.get(self.container_data["Id"])

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.docker_client.api.stop(self.container_data)
        self.docker_client.api.remove_container(self.container_data)


class LiveContainer(ContainerSession):
    """
    A container that run a command that "do nothing" indefinitely. The idea is to keep the container alive.
    """

    COMMAND = "tail -f /dev/null"

    def __init__(self, leverage_container, tty=True):
        with CustomEntryPoint(leverage_container, self.COMMAND):
            container_data = leverage_container._create_container(tty)
        super().__init__(leverage_container.client, container_data)


def tar_directory(host_dir_path: Path) -> bytes:
    """
    Compress a local directory on memory as a tar file and return it as bytes.
    """
    bytes_array = io.BytesIO()
    with tarfile.open(fileobj=bytes_array, mode="w") as tar_handler:
        # walk through the directory tree
        for root, dirs, files in os.walk(host_dir_path):
            for f in files:
                # and add each file to the tar file
                file_path = Path(os.path.join(root, f))
                tar_handler.add(
                    os.path.join(root, f),
                    arcname=file_path.relative_to(host_dir_path),
                )

    bytes_array.seek(0)
    # return the whole tar file as a byte array
    return bytes_array.read()


def key_finder(d: dict, target: str, avoid: str = None):
    """
    Iterate over a dict of dicts and/or lists of dicts, looking for a key with value "target".
    Collect and return all the values that matches "target" as key.
    """
    values = []

    for key, value in d.items():
        if isinstance(value, dict):
            # not the target but a dict? keep iterating recursively
            values.extend(key_finder(value, target, avoid))
        elif isinstance(value, list):
            # not a dict but a list? it must be a list of dicts, keep iterating recursively
            for dict_ in [d_ for d_ in value if isinstance(d_, dict)]:
                values.extend(key_finder(dict_, target, avoid))
        elif key == target:
            if avoid and avoid in value:
                # we found a key but the value contains <avoid> so skip it
                continue
            # found the target key, store the value
            return [value]  # return it as an 1-item array to avoid .extend() to split the string

    return values


def get_or_create_section(updater: ConfigUpdater, section_name: str):
    if not updater.has_section(section_name):
        updater.add_section(section_name)
    # add_section doesn't return the section object, so we need to retrieve it either case
    return updater.get_section(section_name)
