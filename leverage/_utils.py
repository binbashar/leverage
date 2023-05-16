"""
    General use utilities.
"""
from subprocess import run
from subprocess import PIPE

from click.exceptions import Exit

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
    This works as a replacement of _prepare_container.
    """

    def __init__(self, container, override_entrypoint=None):
        if container.sso_enabled:
            container._check_sso_token()
            auth_method = f"{container.TF_SSO_ENTRYPOINT} -- "
        elif container.mfa_enabled:
            auth_method = f"{container.TF_MFA_ENTRYPOINT} -- "
            container.environment.update(
                {
                    "AWS_SHARED_CREDENTIALS_FILE": container.environment["AWS_SHARED_CREDENTIALS_FILE"].replace(
                        "tmp", ".aws"
                    ),
                    "AWS_CONFIG_FILE": container.environment["AWS_CONFIG_FILE"].replace("tmp", ".aws"),
                }
            )
        else:
            auth_method = ""

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
        self.container.change_file_ownership(self.container.guest_aws_credentials_dir)


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

    def __init__(self, docker_client, container):
        self.docker_client = docker_client
        self.container = container

    def __enter__(self):
        self.docker_client.api.start(self.container)

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.docker_client.api.stop(self.container)
        self.docker_client.api.remove_container(self.container)
