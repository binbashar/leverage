"""
    Binbash Leverage Command-line tool.
"""

import rich
from packaging.version import Version

import click

from leverage import __version__, conf
from leverage._internals import pass_state

# from leverage.modules.credentials import credentials
from leverage.modules import aws, run, tofu, terraform

# from leverage.modules import run, project, tofu, terraform, tfautomv, kubectl, shell
from leverage.path import NotARepositoryError, PathsHandler


@click.group(invoke_without_command=True)
@click.option("-v", "--verbose", is_flag=True, help="Increase output verbosity.")
@click.version_option(version=__version__)
@pass_state
@click.pass_context
def leverage(context, state, verbose):
    """Leverage Reference Architecture projects command-line tool."""
    # --verbose | -v
    state.verbosity = verbose
    if context.invoked_subcommand is None:
        # leverage called with no subcommand
        click.echo(context.get_help())

    try:
        state.config = conf.load()
    except NotARepositoryError:
        return
    state.paths = PathsHandler(state.config)


# Add modules to leverage
leverage.add_command(run)
# leverage.add_command(project)
leverage.add_command(tofu)
leverage.add_command(tofu, name="tf")
leverage.add_command(terraform)
# leverage.add_command(credentials)
leverage.add_command(aws)
# leverage.add_command(tfautomv)
# leverage.add_command(kubectl)
# leverage.add_command(kubectl, name="kc")
