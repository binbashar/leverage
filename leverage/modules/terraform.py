import re
import hcl2
import click
from click.exceptions import Exit

from leverage import logger
from leverage._internals import pass_state
from leverage._internals import pass_container
from leverage.container import get_docker_client
from leverage.container import TerraformContainer

REGION = (r"global|(?:[a-z]{2}-(?:gov-)?"
          r"(?:central|north|south|east|west|northeast|northwest|southeast|southwest|secret|topsecret)-[1-4])")

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


CONTEXT_SETTINGS = {
    "ignore_unknown_options": True
}


@terraform.command(context_settings=CONTEXT_SETTINGS)
@click.option("--no-backend",
              is_flag=True)
@click.argument("args", nargs=-1)
@pass_container
@click.pass_context
def init(context, tf, no_backend, args):
    """ Initialize this layer. """
    context.invoke(validate_layout) # Validate layout before attempting to initialize Terraform

    backend_config = ["-backend=false" if no_backend else f"-backend-config={tf.TF_BACKEND_TFVARS}"]
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
    exit_code = tf.start_in_layer("destroy", *tf.TF_DEFAULT_ARGS, *args)

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


def _make_layer_backend_key(cwd, account_dir, account_name):
    """ Create expected backend key.

    Args:
        cwd (pathlib.Path): Current Working Directory (Layer Directory)
        account_dir (pathlib.Path): Account Directory
        account_name (str): Account Name

    Returns:
        list: Backend bucket key parts
    """
    layer_path = cwd.relative_to(account_dir)
    layer_path = layer_path.as_posix().split("/")    
    # Remove region directory
    layer_path = layer_path[1:] if re.match(REGION, layer_path[0]) else layer_path
    # Remove layer name prefix
    layer_name_parts = layer_path[0].split("-")
    layer_name_parts = layer_name_parts[1:] if layer_name_parts[0] in ("base", "tools") else layer_name_parts
    layer_path[0] = "-".join(layer_name_parts)
    return [account_name, *layer_path]


@terraform.command("validate-layout")
@pass_container
def validate_layout(tf):
    """ Validate layer conforms to Leverage convention. """
    tf.check_for_layer_location()

    # Check for `environment = <account name>` in account.tfvars
    account_name = tf.account_conf.get("environment")
    logger.info("Checking environment name definition in [bold]account.tfvars[/bold]...")
    if account_name is None:
        logger.error("[red]✘ FAILED[/red]\n")
        raise Exit(1)
    logger.info("[green]✔ OK[/green]\n")

    # Check if account directory name matches with environment name
    if tf.account_dir.stem != account_name:
        logger.warning("[yellow]‼[/yellow] Account directory name does not match environment name.\n"
                       f"  Expected [bold]{account_name}[/bold], found [bold]{tf.account_dir.stem}[/bold]\n")

    config_tf = tf.cwd / "config.tf"
    try:
        config_tf = hcl2.loads(config_tf.read_text()) if config_tf.exists() else {}
        backend_key = config_tf["terraform"][0]["backend"][0]["s3"]["key"].split("/")
    except (KeyError, IndexError):
        logger.error("[red]✘[/red] Malformed [bold]config.tf[/bold] file. Missing Terraform backend bucket key.")
        raise Exit(1)
    except:
        logger.error("[red]✘[/red] Malformed [bold]config.tf[/bold] file. Unable to parse.")
        raise Exit(1)

    # Check backend bucket key
    expected_backend_key = _make_layer_backend_key(tf.cwd, tf.account_dir, account_name)
    logger.info(f"Checking if backend key matches '{'/'.join(expected_backend_key)}/terraform.tfstate'...")
    if backend_key[:-1] == expected_backend_key:
        logger.info("[green]✔ OK[/green]\n")
    else:
        logger.error("[red]✘ FAILED[/red]\n")

    backend_tfvars = tf.account_config_dir / tf.BACKEND_TFVARS
    backend_tfvars = hcl2.loads(backend_tfvars.read_text()) if backend_tfvars.exists() else {}

    logger.info("Checking [bold]backend.tfvars[/bold]:\n")
    names_prefix = f"{tf.project}-{account_name}"

    # Check profile, bucket and dynamo table names:
    for field in ("profile", "bucket", "dynamodb_table"):
        logger.info(f"Checking if {field.replace('_', ' ')} starts with {names_prefix}...")
        if backend_tfvars.get(field, "").startswith(names_prefix):
            logger.info("[green]✔ OK[/green]\n")
        else:
            logger.error("[red]✘ FAILED[/red]\n")

    logger.info("Done.")


@terraform.command("import")
@click.argument("address")
@click.argument("_id", metavar="ID")
@pass_container
def _import(tf, address, _id):
    """ Import a resource. """
    exit_code = tf.start_in_layer("import", *tf.TF_DEFAULT_ARGS, address, _id)

    if exit_code:
        raise Exit(exit_code)
