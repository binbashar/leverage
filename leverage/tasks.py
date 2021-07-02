"""
    Task loading, Task object definition and task creation decorator.
"""
import sys
import importlib
from pathlib import Path
from inspect import getmembers
from inspect import isfunction
from operator import attrgetter

import click
from click.exceptions import Exit

from leverage import __version__
from leverage import logger
from leverage._internals import Module
from leverage._utils import clean_exception_traceback
from leverage.path import get_build_script_path


class NotATaskError(ImportError):
    pass


class MissingParensInDecoratorError(ImportError):
    pass


def task(*dependencies, **options):
    """ Task decorator to mark functions in a build script as tasks to be performed.

    Raises:
        MissingParensInDecorator: When the decorator is most likely being used without parentheses
            on a function.
        NotATask: When any of the task dependencies is not a task.

    Returns:
        Task: the task to be run
    """
    # In
    # ```
    #     @task
    #     def func():
    #         pass
    # ```
    # `func` ends up passed as a dependency to the decorator and becomes indistinguishable from
    # ```
    #     @task(function_not_task)
    #     def func():
    #         pass
    # ```
    # where the dependency provided is a function and not a task. So the need of parentheses is
    # enforced through this check below
    if len(dependencies) == 1 and isfunction(dependencies[0]):
        raise MissingParensInDecoratorError("Possible parentheses missing in function "
                                            f"`{dependencies[0].__name__}` decorator.")

    not_tasks = [dependency.__name__
                 for dependency in dependencies
                 if not Task.is_task(dependency)]

    if not_tasks:
        raise NotATaskError(f"Dependencies {', '.join(not_tasks)} are not tasks. "
                            "They all must be functions decorated with the `@task()` decorator.")

    def _task(func):
        return Task(func, list(dependencies), options)

    return _task


class Task:
    """ Task to be run by Leverage, created from a function with the @task() decorator.
    A task which name starts with an underscore is considered private and, as such, not shown
    when tasks are listed, this can also be explicitly indicated in the decorator.
    An ignored task won't be ran by Leverage.
    """
    def __init__(self, task, dependencies=None, options=None):
        """ Task object initialization

        Args:
            task (function): Function to be called upon task execution.
            dependencies (list(Tasks), optional): List of tasks that must be performed before this
                task is executed. Defaults to an empty list.
            options (dict, optional): Options regarding the task nature:
                - private (bool): Whether the task is private or not. Defaults to False.
                - ignored (bool): When `True` the task won't be executed by Leverage. Defaults to False.
        """
        self.task = task
        self.name = self.task.__name__
        self.doc = self.task.__doc__ or ""

        self.dependencies = [] if dependencies is None else dependencies

        options = {} if options is None else options
        self._private = self.name.startswith("_") or bool(options.get("private", False))
        self._ignored = bool(options.get("ignore", False))

    @classmethod
    def is_task(cls, obj):
        """ Whether the given object is a task or not """
        return isinstance(obj, cls)

    @property
    def is_private(self):
        """ Whether the task is private or not """
        return self._private

    @property
    def is_ignored(self):
        """ Whether the task is ignored or not """
        return self._ignored

    def __call__(self, *args, **kwargs):
        """ Execute the task """
        self.task(*args, **kwargs)

    def __eq__(self, other):
        return (isinstance(other, Task)
                and self.name == other.name
                and self.doc == other.doc)

    def __hash__(self):
        return id(self)


def load_tasks(build_script_filename="build.py"):
    """ Load the tasks in the build script if there is one.

    Args:
        build_script_filename (str, optional): Name of the file containing the defined tasks. Defaults to "build.py".

    Returns:
        Module: Module containing the loaded tasks. An empty module if no build script is found.
    """
    build_script = get_build_script_path(filename=build_script_filename)

    if build_script is None:
        return Module()

    return _load_build_script(build_script=build_script)


def _load_build_script(build_script):
    """ Load build script as module and return the useful bits.
    If build script is malformed the exception trace is printed and the application exits.

    Args:
        build_script (str): Path to the file containing the definition of the tasks.

    Returns:
        Module: Name, tasks and default tasks of the module.
    """
    build_script = Path(build_script)

    # Treat the folder in which the script is as a package to allow
    # relative imports
    package = build_script.parent
    sys.path.append(package.parent.as_posix())

    # Package needs to be imported first
    importlib.import_module(package.name)

    # Load build script as module
    try:
        module = importlib.import_module(f".{build_script.stem}",
                                         package=package.name)

    except (ImportError, ModuleNotFoundError, SyntaxError) as exc:
        # Remove frames in the traceback until we reach the one pertaining to the build
        # script, as to avoid polluting the output with internal leverage calls,
        # only frames of the build script and its dependencies are shown.
        build_script = build_script.as_posix()
        while (exc.__traceback__ is not None
                and exc.__traceback__.tb_frame.f_code.co_filename != build_script):
            exc.__traceback__ = exc.__traceback__.tb_next

        exc = clean_exception_traceback(exception=exc)

        logger.exception("Error in build script.", exc_info=exc)
        raise Exit(1)

    return Module(name=Path(module.__file__).name,
                  tasks=_get_tasks(module=module),
                  default_task=getattr(module, "__DEFAULT__", None))


def _get_tasks(module):
    """ Extract all Task objects from a loaded module.

    Args:
        module (module): Loaded module containing the definition of tasks.

    Returns:
        list: All tasks found in the given module.
    """
    # If there's a default task set, then that task is extracted twice from the
    # module (as the created task and as the `__DEFAULT__` variable value),
    # hence the set, used to avoid repetition
    return list({task for _, task in getmembers(module, Task.is_task)})


_CREDIT_LINE = f"Powered by Leverage {__version__}"
_IGNORED = "Ignored"
_DEFAULT = "Default"


def list_tasks(module):
    """ Print all non-private tasks in a neat table-like format.
    Indicates whether the task is ignored and/or if it is the default one.

    Args:
        module (dict): Dictionary containing all tasks and the module name
    """
    visible_tasks = [task for task in module.tasks if not task.is_private]

    if visible_tasks:
        # Header
        click.echo(f"Tasks in build file `{module.name}`:\n")

        tasks_grid = []

        for task in sorted(visible_tasks, key=attrgetter("name")):
            # Form the attrs column values
            task_attrs = []
            if task == module.default_task:
                task_attrs.append(_DEFAULT)
            if task.is_ignored:
                task_attrs.append(_IGNORED)
            task_attrs = f"[{','.join(task_attrs)}]" if task_attrs else ""
            # Split multiline docstrings to be able to handle them as a column
            doc_lines = task.doc.splitlines()

            tasks_grid.append((task.name, task_attrs, doc_lines))

        name_column_width = max(len(name) for name, _, _ in tasks_grid)
        attr_column_width = max(len(attr) for _, attr, _ in tasks_grid)

        # Body
        for name, attr, doc in tasks_grid:

            doc_line = "" if not doc else doc[0]
            click.echo(f"  {name:<{name_column_width}}  {attr: ^{attr_column_width}}\t{doc_line}")
            # Print the remaining lines of the dosctring with the correct indentation
            for doc_line in doc[1:]:
                click.echo(f"    {'': <{name_column_width + attr_column_width}}\t{doc_line}")

        # Footer
        click.echo(f"\n{_CREDIT_LINE}")

    else:
        click.echo("  No tasks found or no build script present in current directory.")
