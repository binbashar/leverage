"""
    Binbash Leverage Command-line tool.
"""

from packaging.version import Version

import click

from leverage import __version__, conf
from leverage._internals import pass_state
from leverage.modules.aws import aws
from leverage.modules.credentials import credentials
from leverage.modules import run, project, terraform, tfautomv, kubectl, shell
from leverage.path import NotARepositoryError


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

    # if there is a version restriction set, make sure we satisfy it
    try:
        config = conf.load()
    except NotARepositoryError:
        # restrictions are only verified within a leverage project
        return
    minimum_version = config.get("LEVERAGE_CLI_VERSION")
    if minimum_version and Version(__version__) < Version(minimum_version):
        click.echo(
            f"\033[91mWARNING\033[0m\tYour current version ({__version__}) is lower than the required minimum ({minimum_version})."
        )


# Add modules to leverage
leverage.add_command(run)
leverage.add_command(project)
leverage.add_command(terraform)
leverage.add_command(terraform, name="tf")
leverage.add_command(credentials)
leverage.add_command(aws)
leverage.add_command(tfautomv)
leverage.add_command(kubectl)
leverage.add_command(kubectl, name="kc")
leverage.add_command(shell)
