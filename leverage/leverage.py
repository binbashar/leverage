"""
    Binbash Leverage Command-line tool.
"""

import sys
from pathlib import Path
from importlib import util
from inspect import getmembers

import click
from click import ClickException

from leverage import __version__
from .task import Task
from .task import NotATaskError
from .task import MissingParensInDecoratorError
from .path import NotARepositoryError
from .path import get_build_script_path
from ._utils import _list_tasks

from .modules import run


@click.group(invoke_without_command=True)
@click.option("--filename", "-f",
                default="build.py",
                show_default=True,
                help="Name of the build file containing the tasks definitions.")
@click.option("--list-tasks", "-l",
                is_flag=True,
                help="List available tasks to run.")
@click.option("-v", "--verbose",
                is_flag=True,
                help="Increase output verbosity.")
@click.version_option(version=__version__)
@click.pass_context
def leverage(context, filename, list_tasks, verbose):
    """ Leverage Reference Architecture projects command-line tool. """
    context.ensure_object(dict)

    # --verbose | -v
    context.obj["verbose"] = verbose

    # Load build file as a module
    try:
        build_script = get_build_script_path(filename=filename)

    except (NotARepositoryError,
            NotATaskError,
            MissingParensInDecoratorError) as exc:
        raise ClickException(str(exc)) from exc

    module = _load_build_script(build_script=build_script)
    context.obj["module"] = module

    # --list-tasks|-l or leverage invoked with no subcommand
    if list_tasks or context.invoked_subcommand is None:
        _list_tasks(context.obj["module"])


# Add modules to leverage
leverage.add_command(run)


def _load_build_script(build_script):
    """ Load build script as module and return the useful bits.
    If the input is an empty string an empty module named `build.py` is returned.

    Args:
        build_script (str): Path to the file containing the definition of the tasks.

    Returns:
        dict: Name, tasks and default tasks of the module.
    """
    # Return an empty module named `build.py` if no path is given
    if not build_script:
        return {
            "name": "build.py",
            "tasks": [],
            "__DEFAULT__": None
        }

    build_script = Path(build_script)

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
    # module (as the created task and as the `__DEFAULT__` variable value),
    # hence the set, used to avoid repetition
    return list({task for _, task in getmembers(module, Task.is_task)})
