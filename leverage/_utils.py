"""
    General use utilities.
"""

from pathlib import Path
from subprocess import run
from subprocess import PIPE

import hcl2
import lark
from click.exceptions import Exit
from configupdater import ConfigUpdater
from docker import DockerClient
from docker.models.containers import Container

from leverage import logger


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


class ExitError(Exit):
    """
    Raise an Exit exception but also print an error description.
    """

    def __init__(self, exit_code: int, error_description: str):
        logger.error(error_description)
        super(ExitError, self).__init__(exit_code)


def parse_tf_file(file: Path):
    """
    Open and parse an HCL file.
    In case of a parsing error, raise a user-friendly error.
    """
    try:
        content = file.read_text()
        parsed = hcl2.loads(content)
    except lark.exceptions.UnexpectedInput as error:
        raise ExitError(
            1,
            f"Possible invalid expression in file {file.name} near line {error.line}, column {error.column}\n"
            f"{error.get_context(content)}",
        )
    else:
        return parsed


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
