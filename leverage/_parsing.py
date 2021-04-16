"""
    Command line arguments and tasks arguments parsing utilities.
"""
from argparse import ArgumentParser


class InvalidArgumentOrderError(RuntimeError):
    pass


class DuplicateKeywordArgumentError(RuntimeError):
    pass


def _get_argument_parser():
    """ Create the required argument parser.

    Returns:
        argparse.ArgumentParser: argument parser
    """
    parser = ArgumentParser(add_help=False)

    parser.add_argument("tasks",
                        nargs="*",
                        metavar="task",
                        help="Perform specied task(s) and all of its dependencies")
    parser.add_argument("-l", "--list-tasks",
                        action="store_true",
                        help="List available tasks")
    parser.add_argument("-v", "--version",
                        action="store_true",
                        help="Display tool version")
    parser.add_argument("-f", "--file",
                        metavar="file",
                        default="build.py",
                        help="Name of the build file containing the tasks definitions,"
                             " if left unspecified defaults to `build.py`")
    parser.add_argument("-h", "--help",
                        action='store_true',
                        help="Print help information")

    return parser

def _parse_args(arguments):
    """ Parse the arguments for a task and return args and kwargs appropriately

    Args:
        arguments (str): Arguments to parse.

    Raises:
        InvalidArgumentOrderError: When a positional argument is given after keyworded
            arguments are already been specified.
        DuplicateKeywordArgumentError: When a keyworded argument is specified more than once.

    Returns:
        list, dict: Args, and kwargs present in the input string.
    """
    args = []
    kwargs = {}

    if arguments is None:
        return args, kwargs

    arguments = arguments.split(",")

    for argument in arguments:
        if "=" not in argument:
            if kwargs:
                raise InvalidArgumentOrderError(f"Positional argument `{argument}` from task `{{task}}` cannot follow a keyword argument.")

            args.append(argument.strip())

        else:
            key, value = [part.strip() for part in argument.split("=")]
            if key in kwargs:
                raise DuplicateKeywordArgumentError(f"Duplicated keyword argument `{key}` in task `{{task}}`.")

            kwargs[key] = value

    return args, kwargs
