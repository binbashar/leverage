"""
	Definitions for internal use of the cli.
"""
import click
from click import Option
from click import UsageError

from leverage.logger import get_verbosity


class Module:
    """ Module containing all tasks to be run. """
    def __init__(self, name="build.py", tasks=None, default_task=None):
        self.name = name
        self.tasks = tasks if tasks is not None else []
        self.default_task = default_task

    def __eq__(self, other):
        return (self.name == other.name
                and self.tasks == other.tasks
                and self.default_task == other.default_task)


class State:
    """ Internal state of the application. """
    def __init__(self):
        self._verbosity = None
        self.module = Module()

    @property
    def verbosity(self):
        return self._verbosity

    @verbosity.setter
    def verbosity(self, verbose):
        self._verbosity = get_verbosity(verbose=verbose)


pass_state =  click.make_pass_decorator(State, ensure=True)


class MutuallyExclusiveOption(Option):
    """ Click option that allows implementation of mutual exclusivity between options. """
    def __init__(self, *args, **kwargs):
        self.conflicting_options = kwargs.pop("conflicting_options")

        kwargs["help"] = f"{kwargs.get('help', '')} Option is mutually exclusive with {', '.join(self.conflicting_options)}.".strip()
        super().__init__(*args, **kwargs)

    def handle_parse_result(self, ctx, opts, args):
        current_option = self.consume_value(ctx, opts)[0]

        for parameter in ctx.command.get_params(ctx):
            if (parameter is not self
                    and parameter.human_readable_name in self.conflicting_options
                    and parameter.consume_value(ctx, opts)[0]):
                if current_option:
                    raise UsageError(f"Illegal use: Option '{self.name}' is mutually exclusive "
                                     f"with option '{parameter.human_readable_name}'.")

                self.required = None

        return super().handle_parse_result(ctx, opts, args)
