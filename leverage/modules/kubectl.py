from leverage._internals import pass_state
from leverage._internals import pass_container
from leverage.container import get_docker_client
from leverage.containers.kubectl import KubeCtlContainer

import click

from leverage.modules.utils import _handle_subcommand

CONTEXT_SETTINGS = {"ignore_unknown_options": True}


@click.group(invoke_without_command=True, context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@pass_state
@click.pass_context
def kubectl(context, state, args):
    """Run Kubectl commands in a custom containerized environment."""
    state.container = KubeCtlContainer(get_docker_client())
    if not args or (args and args[0] != "discover"):
        state.container.paths.check_for_layer_location()
    state.container.ensure_image()
    _handle_subcommand(context=context, cli_container=state.container, args=args)


@kubectl.command(context_settings=CONTEXT_SETTINGS)
@pass_container
def shell(kctl: KubeCtlContainer):
    """Spawn a shell with the kubectl credentials pre-configured."""
    kctl.start_shell()


@kubectl.command(context_settings=CONTEXT_SETTINGS)
@pass_container
def configure(kctl: KubeCtlContainer):
    """Automatically add the EKS cluster from the layer into your kubectl config file."""
    kctl.configure()


@kubectl.command(context_settings=CONTEXT_SETTINGS)
@pass_container
def discover(kctl: KubeCtlContainer):
    kctl.discover()
