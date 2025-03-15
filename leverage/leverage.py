"""
    Binbash Leverage Command-line tool.
"""

import rich
from packaging.version import Version

import click

from leverage import __version__, conf, MINIMUM_VERSIONS
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

    # check if the current versions are lower than the minimum required
    if not (current_values := config.get("TERRAFORM_IMAGE_TAG")):
        # at some points of the project (the init), the config file is not created yet
        return
    # validate both TOOLBOX and TF versions
    for key, current in zip(MINIMUM_VERSIONS, current_values.split("-")):
        if Version(current) < Version(MINIMUM_VERSIONS[key]):
            rich.print(
                f"[red]WARNING[/red]\tYour current {key} version ({current}) is lower than the required minimum ({MINIMUM_VERSIONS[key]})."
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
