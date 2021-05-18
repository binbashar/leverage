"""
    Tasks running module.
"""
import re

import click
from click import ClickException

from .._utils import _list_tasks
from ..logger import get_logger
from ..logger import attach_build_handler
from .._parsing import _parse_args
from .._parsing import InvalidArgumentOrderError
from .._parsing import DuplicateKeywordArgumentError


_TASK_PATTERN = re.compile(r"^(?P<name>[^\[\],\s]+)(\[(?P<arguments>[^\]]*)\])?$")


_build_logger = None


class MalformedTaskArgumentError(RuntimeError):
    pass


class TaskNotFoundError(RuntimeError):
    pass


@click.command()
@click.argument("tasks", nargs=-1)
@click.pass_obj
def run(obj, tasks):
    """ Perform specified task(s) and all of its dependencies.

    When no task is given, the default (__DEFAULT__) task is run, if no default task has been defined, all available tasks are listed.
    """
    module = obj["module"]

    global _build_logger
    _build_logger = get_logger("build")
    # Attach a special filter to build logger as to add the name of the build script to every log record
    attach_build_handler(logger=_build_logger, build_script_name=module["name"])

    if tasks:
        # Run the given tasks
        try:
            tasks_to_run = _prepare_tasks_to_run(module, tasks)

        except (TaskNotFoundError,
                MalformedTaskArgumentError) as exc:
            raise ClickException(str(exc)) from exc

        _run_tasks(tasks=tasks_to_run)

    else:
        # Run the default task or  available tasks
        default_task = module["__DEFAULT__"]
        if default_task is not None:
            prepared_default_task = [(default_task, [], {})]
            _run_tasks(prepared_default_task)

        else:
            _list_tasks(module)


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

    Returns:
        list(tuple): List of tasks paired with their corresponding args and kwargs as provided by the user.
    """
    tasks = []
    for input_task in input_tasks:
        match = _TASK_PATTERN.match(input_task)
        if not match:
            raise MalformedTaskArgumentError(f"Malformed task argument in `{input_task}`.")

        name = match.group("name")
        arguments = match.group("arguments")

        try:
            args, kwargs = _parse_args(arguments=arguments)

        except (InvalidArgumentOrderError,
                DuplicateKeywordArgumentError) as exc:
            raise ClickException(str(exc).format(task=name)) from exc

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
