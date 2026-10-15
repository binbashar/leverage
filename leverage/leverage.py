"""
    Binbash Leverage Command-line tool.
"""

import click

from leverage import __version__, conf
from leverage._internals import pass_state
from leverage.path import NotARepositoryError, build_paths_and_environment, is_project_yaml_only_bootstrap
from leverage.modules import aws, credentials, run, project, tofu, terraform, tfautomv, kubectl


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

    # The `project` commands bootstrap a project, so they run before its configuration exists.
    # `project init` creates the git repository, so from that point on the config loads fine but
    # still holds no project name, and building the paths would fail on a legitimate invocation.
    if context.invoked_subcommand == project.name:
        return

    # `credentials configure` can legitimately run right after `project init` and before
    # `project create`: only project.yaml exists, so no project name can be resolved yet and
    # PathsHandler would abort. The `credentials` group callback derives the project name from
    # project.yaml and builds state.paths itself in that case.
    if context.invoked_subcommand == credentials.name and is_project_yaml_only_bootstrap():
        return

    state.paths, state.environment = build_paths_and_environment(state.config)


# Add modules to leverage
leverage.add_command(run)
leverage.add_command(project)
leverage.add_command(tofu)
leverage.add_command(tofu, name="tf")
leverage.add_command(terraform)
leverage.add_command(credentials)
leverage.add_command(aws)
leverage.add_command(tfautomv)
leverage.add_command(kubectl)
leverage.add_command(kubectl, name="kc")
