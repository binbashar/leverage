"""
	Definitions for internal use of the cli.
"""

from functools import wraps

import click

from leverage._utils import ExitError
from leverage.logger import get_verbosity


class Module:
    """Module containing all tasks to be run."""

    def __init__(self, name="build.py", tasks=None, default_task=None):
        self.name = name
        self.tasks = tasks if tasks is not None else []
        self.default_task = default_task

    def __eq__(self, other):
        return self.name == other.name and self.tasks == other.tasks and self.default_task == other.default_task


class State:
    """Internal state of the application."""

    def __init__(self):
        self._verbosity = None
        self.module = Module()
        self.config = None
        self._paths = None
        self.runner = None
        self.environment = None

    @property
    def paths(self):
        # Unset outside a project: the leverage callback leaves it so, for the commands that work anywhere
        if self._paths is None:
            raise ExitError(1, "Out of Leverage project context. Please cd into a Leverage project directory first.")
        return self._paths

    @paths.setter
    def paths(self, paths):
        self._paths = paths

    @property
    def has_paths(self):
        return self._paths is not None

    @property
    def verbosity(self):
        return self._verbosity

    @verbosity.setter
    def verbosity(self, verbose):
        self._verbosity = get_verbosity(verbose=verbose)


pass_state = click.make_pass_decorator(State, ensure=True)


def pass_runner(command):
    """Decorator to pass the current runner (Terraform/OpenTofu runner) to the command."""

    @wraps(command)
    def new_command(*args, **kwargs):
        ctx = click.get_current_context()

        return command(ctx.obj.runner, *args, **kwargs)

    return new_command


def pass_paths(command):
    """Decorator to pass the current project paths to the command."""

    @wraps(command)
    def new_command(*args, **kwargs):
        ctx = click.get_current_context()

        return command(ctx.obj.paths, *args, **kwargs)

    return new_command


def pass_environment(command):
    """Decorator to pass the current environment to the command."""

    @wraps(command)
    def new_command(*args, **kwargs):
        ctx = click.get_current_context()

        return command(ctx.obj.environment, *args, **kwargs)

    return new_command
