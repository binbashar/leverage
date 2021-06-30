"""
    Command line arguments and tasks arguments parsing utilities.
"""
class InvalidArgumentOrderError(RuntimeError):
    pass


class DuplicateKeywordArgumentError(RuntimeError):
    pass


def parse_task_args(arguments):
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
