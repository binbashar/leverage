"""
	Definitions for internal use of the cli.
"""

from functools import wraps

import click

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
        self.container = None

    @property
    def verbosity(self):
        return self._verbosity

    @verbosity.setter
    def verbosity(self, verbose):
        self._verbosity = get_verbosity(verbose=verbose)


pass_state = click.make_pass_decorator(State, ensure=True)


def pass_container(command):
    """Decorator to pass the current container to the command."""

    @wraps(command)
    def new_command(*args, **kwargs):
        ctx = click.get_current_context()

        return command(ctx.obj.container, *args, **kwargs)

    return new_command
