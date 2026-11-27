"""
General use utilities.
"""

from configparser import NoOptionError
from contextlib import suppress
from pathlib import Path
from subprocess import PIPE, run
from typing import List, Optional

import hcl2
import lark
from click.exceptions import ClickException
from configupdater import ConfigUpdater

from leverage import logger

# Credentials, SSO tokens and their caches are readable by their owner only, as the AWS CLI does
PRIVATE_FILE_MODE = 0o600
PRIVATE_DIR_MODE = 0o700


def make_private_dir(path: Path) -> None:
    """Create the directory, and its parents, if missing, and leave it accessible only to its owner.

    An existing directory is tightened too; one owned by another user is left as it is."""
    path.mkdir(mode=PRIVATE_DIR_MODE, parents=True, exist_ok=True)
    with suppress(PermissionError):
        path.chmod(PRIVATE_DIR_MODE)


def make_private_file(path: Path) -> None:
    """Create the file if missing, and leave it readable and writable only by its owner, before any secret is
    written to it. An existing file is tightened too."""
    path.touch(mode=PRIVATE_FILE_MODE, exist_ok=True)
    path.chmod(PRIVATE_FILE_MODE)


def write_private_file(path: Path, text: str) -> None:
    """Write the text to a file only its owner can read (see `make_private_file`)."""
    make_private_file(path)
    path.write_text(text)


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

    # A list, no shell: the commands are the cli's own (`clone <template repo> <dir>`, `init`, ...)
    run(command, stdout=PIPE, stderr=PIPE, check=True)  # noqa: S603


class ExitError(ClickException):
    """
    Raise an Exit exception but also print an error description.
    """

    def __init__(self, exit_code: int, error_description: str):
        # Newer click releases declare exit_code as a class variable (1 for every ClickException), but click reads
        # it from the instance when exiting: setting it here gives each error its own code. `unused-ignore` keeps
        # mypy quiet on the click releases that don't declare it so.
        self.exit_code = exit_code  # type: ignore[misc, unused-ignore]
        super(ExitError, self).__init__(message=error_description)

    def show(self):
        logger.error(self.message)


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


def key_finder(d: dict, target: str, avoid: Optional[str] = None) -> List[str]:
    """
    Iterate over a dict of dicts and/or lists of dicts, looking for a key with value "target".
    Collect and return all the values that matches "target" as key.
    """
    values: List[str] = []

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


def get_option_value(updater: ConfigUpdater, section_name: str, option: str) -> str:
    """Value of an option, which must have one: an option with no value (no `=`) counts as missing."""
    value = updater.get(section_name, option).value
    if value is None:
        raise NoOptionError(option, section_name)
    return value


def get_or_create_section(updater: ConfigUpdater, section_name: str):
    if not updater.has_section(section_name):
        updater.add_section(section_name)
    # add_section doesn't return the section object, so we need to retrieve it either case
    return updater.get_section(section_name)
