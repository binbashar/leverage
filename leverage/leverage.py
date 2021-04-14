"""
    Binbash Leverage Command-line Task Runner
"""

import re
import sys
from pathlib import Path
from importlib import util
from inspect import getmembers

from leverage import __version__

from .task import Task
from .task import NotATaskError
from .task import MissingParensInDecoratorError
from .path import NoBuildScriptFoundError
from .path import get_build_script_path
from .logging import get_logger
from .logging import _attach_build_handler
from ._parsing import _parse_args
from ._parsing import _get_argument_parser
from ._parsing import InvalidArgumentOrderError
from ._parsing import DuplicateKeywordArgumentError


_TASK_PATTERN = re.compile(r"^(?P<name>[^\[]+)(\[(?P<arguments>[^\]]*)\])?$")
_CREDIT_LINE = f"Powered by Leverage {__version__} - A Lightweight Python Build Tool based on Pynt."


_logger = get_logger(name="leverage", level="INFO")
_build_logger = get_logger(name="build", level="INFO")


class MalformedTaskArgumentError(RuntimeError):
    pass


class TaskNotFoundError(RuntimeError):
    pass


def build(args):
    """ Parse received arguments and execute the required action.

    Args:
        args (list): Arguments as received from command line.
    """
    parser = _get_argument_parser()
    args = parser.parse_args(args=args)

    # -v | --version
    if args.version:
        _print_version()

    # Load build file as a module
    try:
        build_script = Path(get_build_script_path(filename=args.file))
        module = _load_build_script(build_script=build_script)

    except (NoBuildScriptFoundError,
            NotATaskError,
            MissingParensInDecoratorError) as exc:
        _terminate(error_message=str(exc))

    # Attach a special filter as to add the name of the build script to every log record
    _attach_build_handler(logger=_build_logger, build_script_name=module["name"])

    # -h | --help
    if args.help:
        parser.print_help()
    # -l
    elif args.list_tasks:
        _print_tasks(module)
    # no args - run default task or print available tasks
    elif not args.tasks:
        default_task = module["__DEFAULT__"]
        if default_task is not None:
            prepared_default_task = [(default_task, [], {})]
            _run_tasks(prepared_default_task)
        else:
            _print_tasks(module)
    # tasks - run the given tasks
    else:
        try:
            tasks_to_run = _prepare_tasks_to_run(module, args.tasks)

        except TaskNotFoundError as exc:
            _terminate(error_message=str(exc))

        _run_tasks(tasks=tasks_to_run)

def _load_build_script(build_script):
    """ Load build script as module and return the useful bits.

    Args:
        build_script (pathlib.Path): File containing the definition of the tasks.

    Returns:
        dict: Name, tasks and default tasks of the module.
    """
    # Allow importing modules relatively to the script
    build_script_directory = build_script.parent.resolve().as_posix()
    sys.path.append(build_script_directory)

    # Load build script as module
    spec = util.spec_from_file_location(name=build_script.stem,
                                        location=build_script)
    module = util.module_from_spec(spec)
    sys.modules[build_script.stem] = module
    spec.loader.exec_module(module)

    return {
        "name": Path(module.__file__).name,
        "tasks": _get_tasks(module=module),
        "__DEFAULT__": getattr(module, "__DEFAULT__", None)
    }

def _get_tasks(module):
    """ Extract all Task objects from a loaded module.

    Args:
        module (module): Loaded module containing the definition of tasks.

    Returns:
        list: All tasks found in the given module.
    """
    # If there's a default task set, then that task is extracted twice from the
    # module (as the created task an as the `__DEFAULT__` variable value),
    # hence, the set, used to avoid repetition
    return list({task for _, task in getmembers(module, Task.is_task)})

def _prepare_tasks_to_run(module, input_tasks):
    """ Validate input tasks and arguments and pair them with the corresponding module's task.

    Args:
        module (dict): Dict containing the tasks from the build script.
        input_tasks (list): Strings containing the tasks to invoke and their arguments as received
            from user input.

    Raises:
        MalformedTaskArgumentError: When the string representing the invocation of a task does not conform
            to the required pattern.
        TaskNotFoundError: When the specified task is not found in the ones defined in the build script.
        AmbiguousTaskNameError: When a given task name matches with multiple defined tasks.

    Returns:
        list(tuple): List of tasks paired with their corresponding args and kwargs as provided by the user.
    """
    tasks = []
    for input_task in input_tasks:
        match = _TASK_PATTERN.match(input_task)
        if not match:
            raise MalformedTaskArgumentError(f"Malformed task argument in {input_task}")

        name = match.group("name")
        arguments = match.group("arguments")

        try:
            args, kwargs = _parse_args(arguments=arguments)

        except (InvalidArgumentOrderError,
                DuplicateKeywordArgumentError) as exc:
            _terminate(error_message=str(exc).format(task=name))

        task = [task for task in module["tasks"] if task.name == name]

        if not task:
            raise TaskNotFoundError(f"Unrecognized task `{name}`.")

        tasks.append((task[0], args, kwargs))

    return tasks

def _run_tasks(tasks):
    """ Run the tasks provided.

    Args:
        tasks (list(tuple)): List of 3-tuples containing a task and it's positional and keyword arguments to run.
    """
    completed_tasks = set()
    for task, args, kwargs in tasks:
        # Remove current task from dependencies set to force it to run, as it was invoked by the user explicitly
        completed_tasks.discard(task)
        _run(task, completed_tasks, *args, **kwargs)

def _run(task, completed_tasks, *args, **kwargs):
    """ Run the given task and all it's required dependencies, keeping track of all the already
    completed tasks as not to repeat them.

    Args:
        task (list): Tasks to run.
        completed_tasks (set): Tasks that have already ran.

    Returns:
        set: Updated set of already executed tasks.
    """
    # Satisfy dependencies recursively.
    for dependency in task.dependencies:
        _completed_tasks = _run(dependency, completed_tasks)
        completed_tasks.update(_completed_tasks)

    if task not in completed_tasks:

        if task.is_ignored:
            _build_logger.info(f"Ignoring task `{task.name}`")

        else:
            _build_logger.info(f"Starting task `{task.name}`")

            try:
                task(*args,**kwargs)
            except:
                _build_logger.critical(f"Error in task `{task.name}`")
                _build_logger.critical("Aborting build")
                raise

            _build_logger.info(f"Completed task `{task.name}`")

        completed_tasks.add(task)

    return completed_tasks

def _print_version():
    """ Print leverage version and quit. """
    _logger.info(f"leverage {__version__}")
    sys.exit(0)

def _print_tasks(module):
    """ Print all non-private tasks in a neat table-like format.
    Indicates whether the task is ignored and/or if it is the default one.

    Args:
        module (dict): Dictionary containing all tasks and the module name
    """
    IGNORED = "Ignored"
    DEFAULT = "Default"

    # Header
    print(f"Tasks in build file `{module['name']}`:\n")

    visible_tasks = [task for task in module["tasks"] if not task.is_private]

    tasks_grid = []
    for task in sorted(visible_tasks, key=attrgetter("name")):
        # Form the attrs column values
        task_attrs = []
        if task == module["__DEFAULT__"]:
            task_attrs.append(DEFAULT)
        if task.is_ignored:
            task_attrs.append(IGNORED)
        task_attrs = f"[{','.join(task_attrs)}]" if task_attrs else ""

        tasks_grid.append((task.name, task_attrs, task.doc))

    name_column_width = max(len(name) for name, _, _ in tasks_grid)
    attr_column_width = max(len(attr) for _, attr, _ in tasks_grid)

    # Body
    for name, attr, doc in tasks_grid:
        print(f"  {name:<{name_column_width}}  {attr: ^{attr_column_width}}\t{doc}")

    # Footer
    print(f"\n{_CREDIT_LINE}")

def _terminate(error_message):
    """ Print error message and terminate program.

    Args:
        error_message (str): Error message to be displayed upon termination.
    """
    _logger.error(f"{error_message} Exiting.")
    sys.exit(1)

def main():
    """ Leverage entrypoint. """
    build(sys.argv[1:])
