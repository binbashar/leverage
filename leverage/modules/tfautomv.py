import click
from click.exceptions import Exit

from leverage._internals import pass_state
from leverage._internals import pass_container
from leverage.container import get_docker_client
from leverage.container import TFautomvContainer

REGION = (
    r"global|(?:[a-z]{2}-(?:gov-)?"
    r"(?:central|north|south|east|west|northeast|northwest|southeast|southwest|secret|topsecret)-[1-4])"
)


@click.group()
@pass_state
def tfautomv(state):
    """Run TFAutomv commands in a custom containerized environment that provides extra functionality when interacting
    with your cloud provider such as handling multi factor authentication for you.
    All terraform subcommands that receive extra args will pass the given strings as is to their corresponding Terraform
    counterparts in the container. For example as in `leverage terraform apply -auto-approve` or
    `leverage terraform init -reconfigure`
    """
    state.container = TFautomvContainer(get_docker_client())
    state.container.ensure_image()


CONTEXT_SETTINGS = {"ignore_unknown_options": True}


@tfautomv.command(context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1)
@pass_container
def run(tf, args):
    """Generate a move tf file for this layer."""
    exit_code = tf.start_in_layer(*args)

    if exit_code:
        raise Exit(exit_code)
