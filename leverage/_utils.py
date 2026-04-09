"""
    General use utilities.
"""

from pathlib import Path
from subprocess import PIPE, run
from typing import List, Optional

import hcl2
import lark
from click.exceptions import ClickException
from configupdater import ConfigUpdater

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


class ExitError(ClickException):
    """
    Raise an Exit exception but also print an error description.
    """

    def __init__(self, exit_code: int, error_description: str):
        self.exit_code = exit_code
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


def get_or_create_section(updater: ConfigUpdater, section_name: str):
    if not updater.has_section(section_name):
        updater.add_section(section_name)
    # add_section doesn't return the section object, so we need to retrieve it either case
    return updater.get_section(section_name)
