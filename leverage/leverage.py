"""
    Binbash Leverage Command-line Task Runner
"""

import sys
from pathlib import Path
from importlib import util
from inspect import getmembers

from leverage import __version__

from .task import Task
from .task import NotATaskError
from .task import MissingParensInDecoratorError
from .path import NotARepositoryError
from .path import get_build_script_path

    # Load build file as a module
    try:

    except (NotARepositoryError,
            NotATaskError,
            MissingParensInDecoratorError) as exc:
    else:



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
def _print_version():
    """ Print leverage version and quit. """
    _logger.info(f"leverage {__version__}")
    sys.exit(0)

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
