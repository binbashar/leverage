"""
    General use utilities.
"""
import functools
from subprocess import run
from subprocess import PIPE

from click.exceptions import Exit

from leverage import logger


def clean_exception_traceback(exception):
    """ Delete special local variables from all frames of an exception's traceback
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
    """ Run the given git command.

    Args:
        command (str): Complete git command with or without the binary name.
    """
    command = command.split()
    command = ["git"] + command if command[0] != "git" else command

    run(command, stdout=PIPE, stderr=PIPE, check=True)


def chain_commands(commands: list, chain: str = " && ") -> str:
    return f"bash -c \"{chain.join(commands)}\""


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


class EmptyEntryPoint(CustomEntryPoint):
    """
    Force an empty entrypoint. This will let you execute any commands freely.
    """

    def __init__(self, container):
        super(EmptyEntryPoint, self).__init__(container, entrypoint="")


def refresh_aws_credentials(func):
    """
    Use this decorator in the case you want to make sure you will have fresh tokens to interact with AWS
    during the execution of your wrapped method.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        container = args[0]  # this is the "self" of the method you are decorating; a LeverageContainer instance

        if container.sso_enabled:
            container._check_sso_token()
            auth_method = container.TF_SSO_ENTRYPOINT
        elif container.mfa_enabled:
            auth_method = container.TF_MFA_ENTRYPOINT
            # TODO: ask why this was necessary
            container.environment.update({
                "AWS_SHARED_CREDENTIALS_FILE": container.environment["AWS_SHARED_CREDENTIALS_FILE"].replace("tmp", ".aws"),
                "AWS_CONFIG_FILE": container.environment["AWS_CONFIG_FILE"].replace("tmp", ".aws"),
            })
        else:
            # no auth method found: skip the refresh
            return func(*args, **kwargs)

        logger.info("Fetching  AWS credentials...")
        with CustomEntryPoint(container, f"{auth_method} -- echo"):
            # this simple echo "Fetching..." will run the SSO/MFA entrypoints underneath
            # that takes care of the token refresh
            exit_code = container._start("Fetching done.")
            if exit_code:
                raise Exit(exit_code)
            if container.mfa_enabled:
                # we need to revert to the original values, otherwise other tools that rely on awscli, like kubectl
                # won't find the credentials
                container.environment.update({
                    "AWS_SHARED_CREDENTIALS_FILE": container.environment["AWS_SHARED_CREDENTIALS_FILE"].replace(".aws", "tmp"),
                    "AWS_CONFIG_FILE": container.environment["AWS_CONFIG_FILE"].replace(".aws", "tmp"),
                })

        # we should have a valid token at this point, now execute the original method
        return func(*args, **kwargs)

    return wrapper
