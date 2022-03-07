import click
from click.exceptions import Exit

from leverage._internals import pass_state
from leverage._internals import pass_container
from leverage.container import get_docker_client
from leverage.container import TerraformContainer


@click.group()
@pass_state
def terraform(state):
    """ Run Terraform commands in a custom containerized environment that provides extra functionality when interacting
    with your cloud provider such as handling multi factor authentication for you.
    All terraform subcommands that receive extra args will pass the given strings as is to their corresponding Terraform
    counterparts in the container. For example as in `leverage terraform apply -auto-approve` or
    `leverage terraform init -reconfigure`
    """
    state.container = TerraformContainer(get_docker_client())
    state.container.ensure_image()


CONTEXT_SETTINGS = {"ignore_unknown_options": True}


@terraform.command(context_settings=CONTEXT_SETTINGS)
@click.option("--no-backend",
              is_flag=True)
@click.argument("args", nargs=-1)
@pass_container
def init(tf, no_backend, args):
    """ Initialize this layer. """
    backend_config = ["-backend=false" if no_backend else f"-backend-config={tf.BACKEND_TFVARS}"]
    args = backend_config + list(args)
    exit_code = tf.start_in_layer("init", *args)

    if exit_code:
        raise Exit(exit_code)


@terraform.command(context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1)
@pass_container
def plan(tf, args):
    """ Generate an execution plan for this layer. """
    exit_code = tf.start_in_layer("plan", *tf.TF_DEFAULT_ARGS, *args)

    if exit_code:
        raise Exit(exit_code)


@terraform.command(context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1)
@pass_container
def apply(tf, args):
    """ Build or change the infrastructure in this layer. """
    exit_code = tf.start_in_layer("apply", *tf.TF_DEFAULT_ARGS, *args)

    if exit_code:
        raise Exit(exit_code)


@terraform.command(context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1)
@pass_container
def output(tf, args):
    """ Show all output variables of this layer. """
    tf.start_in_layer("output", *args)


@terraform.command(context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1)
@pass_container
def destroy(tf, args):
    """ Destroy infrastructure in this layer. """
    exit_code = tf.start_in_layer("destroy", *tf.TF_DEFAULTS_ARGS, *args)

    if exit_code:
        raise Exit(exit_code)


@terraform.command()
@pass_container
def version(tf):
    """ Print version. """
    tf.disable_authentication()
    tf.start("version")


@terraform.command()
@click.option("--mfa",
              is_flag=True,
              default=False,
              help="Enable Multi Factor Authentication upon launching shell.")
@click.option("--sso",
              is_flag=True,
              default=False,
              help="Enable SSO Authentication upon launching shell.")
@pass_container
def shell(tf, mfa, sso):
    """ Open a shell into the Terraform container in this layer. """
    tf.disable_authentication()
    if sso:
        tf.enable_sso()

    if mfa:
        tf.enable_mfa()

    tf.start_shell()


@terraform.command("format")
@click.option("--check",
              is_flag=True,
              help="Only perform format checking, do not rewrite the files.")
@pass_container
def _format(tf, check):
    """ Check if all files meet the canonical format and rewrite them accordingly. """
    args = ["-recursive"]
    if check:
        args.extend(["-check", tf.WORKING_DIR])

    tf.disable_authentication()
    tf.start("fmt", *args)


@terraform.command()
@pass_container
def validate(tf):
    """ Validate code of the current directory. Previous initialization might be needed. """
    tf.disable_authentication()
    tf.start("validate")


@terraform.command("import")
@click.argument("address")
@click.argument("_id", metavar="ID")
@pass_container
def _import(tf, address, _id):
    """ Import a resource. """
    exit_code = tf.start_in_layer("import", *tf.TF_DEFAULT_ARGS, address, _id)

    if exit_code:
        raise Exit(exit_code)
