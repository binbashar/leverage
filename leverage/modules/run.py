"""
    Tasks running module.
"""
import re

import click
from click.exceptions import Exit

from leverage import logger
from leverage.tasks import list_tasks
from leverage.logger import get_tasks_logger
from leverage._parsing import parse_task_args
from leverage._parsing import InvalidArgumentOrderError
from leverage._parsing import DuplicateKeywordArgumentError
from leverage._utils import clean_exception_traceback
from leverage._internals import pass_state


_TASK_PATTERN = re.compile(r"^(?P<name>[^\[\],\s]+)(\[(?P<arguments>[^\]]*)\])?$")

_logger = None


class MalformedTaskArgumentError(RuntimeError):
    pass


class TaskNotFoundError(RuntimeError):
    pass


@click.command()
@click.argument("tasks", nargs=-1)
@pass_state
def run(state, tasks):
    """ Perform specified task(s) and all of its dependencies.

    When no task is given, the default (__DEFAULT__) task is run, if no default task has been defined, all available tasks are listed.
    """
    global _logger
    _logger = get_tasks_logger()

    if tasks:
        # Run the given tasks
        try:
            tasks_to_run = _prepare_tasks_to_run(state.module, tasks)

        except (TaskNotFoundError,
                MalformedTaskArgumentError) as exc:
            logger.error(str(exc))
            raise Exit(1)

        _run_tasks(tasks=tasks_to_run)

    else:
        # Run the default task or list available tasks
        default_task = state.module.default_task
        if default_task is not None:
            prepared_default_task = [(default_task, [], {})]
            _run_tasks(prepared_default_task)

        else:
            list_tasks(state.module)


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
            args, kwargs = parse_task_args(arguments=arguments)

        except (InvalidArgumentOrderError,
                DuplicateKeywordArgumentError) as exc:
            logger.error(str(exc).format(task=name))
            raise Exit(1)

        task = [task for task in module.tasks if task.name == name]

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
            _logger.info(f"[bold yellow]⤳[/bold yellow] Ignoring task [bold italic]{task.name}[/bold italic]")

        else:
            _logger.info(f"[bold yellow]➜[/bold yellow] Starting task [bold italic]{task.name}[/bold italic]")

            try:
                task(*args, **kwargs)
            except Exception as exc:
                # Remove the two topmost frames of the traceback since they are internal leverage function calls,
                # only frames pertaining to the build script and its dependencies are shown.
                exc.__traceback__ = exc.__traceback__.tb_next.tb_next
                exc = clean_exception_traceback(exception=exc)

                _logger.exception(f"[bold red]![/bold red] Error in task [bold italic]{task.name}[/bold italic]", exc_info=exc)
                _logger.critical("[red]✘[/red] [bold on red]Aborting build[/bold on red]")
                raise Exit(1)

            _logger.info(f"[green]✔[/green] Completed task [bold italic]{task.name}[/bold italic]")

        completed_tasks.add(task)

    return completed_tasks
