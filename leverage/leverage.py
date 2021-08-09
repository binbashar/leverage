"""
    Binbash Leverage Command-line tool.
"""
import click

from leverage import __version__
from leverage.tasks import load_tasks
from leverage.tasks import list_tasks as _list_tasks
from leverage._internals import pass_state

from leverage.modules import run
from leverage.modules import project
from leverage.modules import terraform
from leverage.modules import credentials


CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help"]
}


@click.group(invoke_without_command=True, context_settings=CONTEXT_SETTINGS)
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
@pass_state
@click.pass_context
def leverage(context, state, filename, list_tasks, verbose):
    """ Leverage Reference Architecture projects command-line tool. """
    # --verbose | -v
    state.verbosity = verbose

    # Load build file as a module
    state.module = load_tasks(build_script_filename=filename)

    if context.invoked_subcommand is None:
        # --list-tasks|-l
        if list_tasks:
            _list_tasks(state.module)

        else:
            # leverage called with no subcommand
            click.echo(context.get_help())


# Add modules to leverage
leverage.add_command(run)
leverage.add_command(project)
leverage.add_command(terraform)
leverage.add_command(terraform, name="tf")
leverage.add_command(credentials)
