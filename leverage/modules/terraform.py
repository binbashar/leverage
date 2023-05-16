import re

import hcl2
import click
from click.exceptions import Exit

from leverage import logger
from leverage._internals import pass_state
from leverage._internals import pass_container
from leverage.container import get_docker_client
from leverage.container import TerraformContainer

REGION = (
    r"global|(?:[a-z]{2}-(?:gov-)?"
    r"(?:central|north|south|east|west|northeast|northwest|southeast|southwest|secret|topsecret)-[1-4])"
)


# ###########################################################################
# CREATE THE TERRAFORM GROUP
# ###########################################################################
@click.group()
@pass_state
def terraform(state):
    """Run Terraform commands in a custom containerized environment that provides extra functionality when interacting
    with your cloud provider such as handling multi factor authentication for you.
    All terraform subcommands that receive extra args will pass the given strings as is to their corresponding Terraform
    counterparts in the container. For example as in `leverage terraform apply -auto-approve` or
    `leverage terraform init -reconfigure`
    """
    state.container = TerraformContainer(get_docker_client())
    state.container.ensure_image()


CONTEXT_SETTINGS = {"ignore_unknown_options": True}

# ###########################################################################
# CREATE THE TERRAFORM GROUP'S COMMANDS
# ###########################################################################
#
# --layers is a ordered comma separated list of layer names
# The layer names are the relative paths of those layers relative to the current directory
# e.g. if CLI is called from /home/user/project/management and this is the tree:
# home
# ├── user
# │   └── project
# │       └── management
# │           ├── global
# │           |   └── security-base
# │           |   └── sso
# │           └── us-east-1
# │               └── terraform-backend
#
# Then all three layers can be initialized as follows:
# leverage tf init --layers us-east-1/terraform-backend,global/security-base,global/sso
#
# It is an ordered list because the layers will be visited in the same order they were
# supplied.
#
layers_option = click.option(
    "--layers",
    type=str,
    default="",
    help="Layers to apply the action to. (an ordered, comma-separated list of layer names)",
)


@terraform.command(context_settings=CONTEXT_SETTINGS)
@click.option("--skip-validation", is_flag=True, help="Skip layout validation.")
@layers_option
@click.argument("args", nargs=-1)
@pass_container
@click.pass_context
def init(context, tf: TerraformContainer, skip_validation, layers, args):
    """
    Initialize this layer.
    """
    layers = invoke_for_all_commands(layers, _init, args, skip_validation)

    # now change ownership on all the downloaded modules and providers
    for layer in layers:
        tf.change_file_ownership(tf.guest_base_path / layer.relative_to(tf.root_dir) / ".terraform")
    # and then providers in the cache folder
    if tf.tf_cache_dir:
        tf.change_file_ownership(tf.tf_cache_dir)


@terraform.command(context_settings=CONTEXT_SETTINGS)
@layers_option
@click.argument("args", nargs=-1)
@pass_container
@click.pass_context
def plan(context, tf, layers, args):
    """Generate an execution plan for this layer."""
    invoke_for_all_commands(layers, _plan, args)


@terraform.command(context_settings=CONTEXT_SETTINGS)
@layers_option
@click.argument("args", nargs=-1)
@pass_container
@click.pass_context
def apply(context, tf, layers, args):
    """Build or change the infrastructure in this layer."""
    invoke_for_all_commands(layers, _apply, args)


@terraform.command(context_settings=CONTEXT_SETTINGS)
@layers_option
@click.argument("args", nargs=-1)
@pass_container
@click.pass_context
def output(context, tf, layers, args):
    """Show all output variables of this layer."""
    invoke_for_all_commands(layers, _output, args)


@terraform.command(context_settings=CONTEXT_SETTINGS)
@layers_option
@click.argument("args", nargs=-1)
@pass_container
@click.pass_context
def destroy(context, tf, layers, args):
    """Destroy infrastructure in this layer."""
    invoke_for_all_commands(layers, _destroy, args)


@terraform.command()
@pass_container
def version(tf):
    """Print version."""
    tf.disable_authentication()
    tf.start("version")


@terraform.command()
@click.option("--mfa", is_flag=True, default=False, help="Enable Multi Factor Authentication upon launching shell.")
@click.option("--sso", is_flag=True, default=False, help="Enable SSO Authentication upon launching shell.")
@pass_container
def shell(tf, mfa, sso):
    """Open a shell into the Terraform container in this layer."""
    tf.disable_authentication()
    if sso:
        tf.enable_sso()

    if mfa:
        tf.enable_mfa()

    tf.start_shell()


@terraform.command("format", context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1)
@pass_container
def _format(tf, args):
    """Check if all files meet the canonical format and rewrite them accordingly."""
    args = args if "-recursive" in args else (*args, "-recursive")
    tf.disable_authentication()
    tf.start("fmt", *args)


@terraform.command()
@pass_container
def validate(tf):
    """Validate code of the current directory. Previous initialization might be needed."""
    tf.disable_authentication()
    tf.start("validate")


@terraform.command("validate-layout")
@pass_container
def validate_layout(tf):
    """Validate layer conforms to Leverage convention."""
    tf.set_backend_key()
    return _validate_layout()


@terraform.command("import")
@click.argument("address")
@click.argument("_id", metavar="ID")
@pass_container
def _import(tf, address, _id):
    """Import a resource."""
    exit_code = tf.start_in_layer("import", *tf.tf_default_args, address, _id)

    if exit_code:
        raise Exit(exit_code)


# ###########################################################################
# HANDLER FOR MANAGING THE BASE COMMANDS (init, plan, apply, destroy, output)
# ###########################################################################
@pass_container
def invoke_for_all_commands(tf, layers, command, args, skip_validation=True):
    """
    Invoke helper for "all" commands.

    Args:
        layers: comma separated value of relative layer path
            e.g.: global/security_audit,us-east-1/tf-backend
        command: init, plan, apply
    """

    # convert layers from string to list
    layers = layers.split(",") if len(layers) > 0 else []

    # based on the location type manage the layers parameter
    if tf.get_location_type() == "layer" and len(layers) == 0:
        # running on a layer
        layers = [tf.cwd]
    elif tf.get_location_type() == "layer":
        # running on a layer but --layers was set
        logger.error("Can not set [bold]--layers[/bold] inside a layer.")
        raise Exit(1)
    elif tf.get_location_type() in ["account", "layers-group"] and len(layers) == 0:
        # running on an account but --layers was not set
        logger.error("[bold]--layers[/bold] has to be set.")
        raise Exit(1)
    elif not tf.get_location_type() in ["account", "layer", "layers-group"]:
        # running outside a layer and account
        logger.error("This command has to be run inside a layer or account directory.")
        raise Exit(1)
    else:
        # running on an account with --layers set
        layers = [tf.cwd / x for x in layers]

    # get current location
    original_location = tf.cwd
    original_working_dir = tf.container_config["working_dir"]

    # validate each layer before calling the execute command
    for layer in layers:
        logger.debug(f"Checking for layer {layer}...")
        # change to current dir and set it in the container
        tf.cwd = layer

        # check layers existence
        if not layer.is_dir():
            logger.error(f"Directory [red]{layer}[/red] does not exist or is not a directory\n")
            raise Exit(1)

        # set the s3 key
        tf.set_backend_key(skip_validation)

        # validate layer
        validate_for_all_commands(layer, skip_validation=skip_validation)

        # change to original dir and set it in the container
        tf.cwd = original_location

    # check layers existence
    for layer in layers:
        if len(layers) > 1:
            logger.info(f"Invoking command for layer {layer}...")

        # change to current dir and set it in the container
        tf.cwd = layer

        # set the working dir
        tf.container_config["working_dir"] = f"{tf.guest_base_path}/{tf.cwd.relative_to(tf.root_dir).as_posix()}"

        # execute the actual command
        command(args=args)

        # change to original dir and set it in the container
        tf.cwd = original_location

        # change to original workgindir
        tf.container_config["working_dir"] = original_working_dir

    return layers


def validate_for_all_commands(layer, skip_validation=False):
    """
    Validate existence of layer and, if set, all the Leverage related stuff
    of each of them

    Args:
        layer: a full layer directory
    """

    logger.debug(f"Checking layer {layer}...")
    if not skip_validation and not _validate_layout():
        logger.error(
            "Layer configuration doesn't seem to be valid. Exiting.\n"
            "If you are sure your configuration is actually correct "
            "you may skip this validation using the --skip-validation flag."
        )
        raise Exit(1)


# ###########################################################################
# BASE COMMAND EXECUTORS
# ###########################################################################
@pass_container
def _init(tf, args):
    """Initialize this layer."""

    args = [
        arg
        for index, arg in enumerate(args)
        if not arg.startswith("-backend-config") or not arg[index - 1] == "-backend-config"
    ]
    args.append(f"-backend-config={tf.backend_tfvars}")

    exit_code = tf.start_in_layer("init", *args)

    if exit_code:
        raise Exit(exit_code)


@pass_container
def _plan(tf, args):
    """Generate an execution plan for this layer."""
    exit_code = tf.start_in_layer("plan", *tf.tf_default_args, *args)

    if exit_code:
        raise Exit(exit_code)


@pass_container
def _apply(tf, args):
    """Build or change the infrastructure in this layer."""
    # if there is a plan, remove all "-var" from the default args
    tf_default_args = tf.tf_default_args
    for arg in args:
        if not arg.startswith("-"):
            tf_default_args = [arg for index, arg in enumerate(tf_default_args) if not arg.startswith("-var")]
            break
    exit_code = tf.start_in_layer("apply", *tf_default_args, *args)

    if exit_code:
        raise Exit(exit_code)


@pass_container
def _output(tf, args):
    """Show all output variables of this layer."""
    tf.start_in_layer("output", *args)


@pass_container
def _destroy(tf, args):
    """Destroy infrastructure in this layer."""
    exit_code = tf.start_in_layer("destroy", *tf.tf_default_args, *args)

    if exit_code:
        raise Exit(exit_code)


# ###########################################################################
# MISC FUNCTIONS
# ###########################################################################
def _make_layer_backend_key(cwd, account_dir, account_name):
    """Create expected backend key.

    Args:
        cwd (pathlib.Path): Current Working Directory (Layer Directory)
        account_dir (pathlib.Path): Account Directory
        account_name (str): Account Name

    Returns:
        list of lists: Backend bucket key parts
    """
    resp = []

    layer_path = cwd.relative_to(account_dir)
    layer_path = layer_path.as_posix().split("/")
    # Check region directory to keep retro compat
    if re.match(REGION, layer_path[0]):
        layer_paths = [layer_path[1:], layer_path]
    else:
        layer_paths = [layer_path]

    curated_layer_paths = []
    # Remove layer name prefix
    for layer_path in layer_paths:
        curated_layer_path = []
        for lp in layer_path:
            if lp.startswith("base-"):
                lp = lp.replace("base-", "")
            elif lp.startswith("tools-"):
                lp = lp.replace("tools-", "")
            curated_layer_path.append(lp)
        curated_layer_paths.append(curated_layer_path)

    curated_layer_paths_retrocomp = []
    for layer_path in curated_layer_paths:
        curated_layer_paths_retrocomp.append(layer_path)
        # check for tf/terraform variants
        for idx, lp in enumerate(layer_path):
            if lp.startswith("tf-"):
                layer_path_tmp = layer_path.copy()
                layer_path_tmp[idx] = layer_path_tmp[idx].replace("tf-", "terraform-")
                curated_layer_paths_retrocomp.append(layer_path_tmp)
                break
            elif lp.startswith("terraform-"):
                layer_path_tmp = layer_path.copy()
                layer_path_tmp[idx] = layer_path_tmp[idx].replace("terraform-", "tf-")
                curated_layer_paths_retrocomp.append(layer_path_tmp)
                break

    curated_layer_paths_withDR = []
    for layer_path in curated_layer_paths_retrocomp:
        curated_layer_paths_withDR.append(layer_path)
        curated_layer_path = []
        append_str = "-dr"
        for lp in layer_path:
            if re.match(REGION, lp):
                curated_layer_path.append(lp)
            else:
                curated_layer_path.append(lp + append_str)
                append_str = ""
        curated_layer_paths_withDR.append(curated_layer_path)

    for layer_path in curated_layer_paths_withDR:
        resp.append([account_name, *layer_path])

    return resp


@pass_container
def _validate_layout(tf):
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
        logger.warning(
            "[yellow]‼[/yellow] Account directory name does not match environment name.\n"
            f"  Expected [bold]{account_name}[/bold], found [bold]{tf.account_dir.stem}[/bold]\n"
        )

    backend_key = tf.backend_key.split("/")

    # Flag to report layout validity
    valid_layout = True

    # Check backend bucket key
    expected_backend_keys = _make_layer_backend_key(tf.cwd, tf.account_dir, account_name)
    logger.info("Checking backend key...")
    logger.info(f"Found: '{'/'.join(backend_key)}'")
    backend_key = backend_key[:-1]

    if backend_key in expected_backend_keys:
        logger.info("[green]✔ OK[/green]\n")
    else:
        exp_message = [f"{'/'.join(x)}/terraform.tfstate" for x in expected_backend_keys]
        logger.info(f"Expected one of: {';'.join(exp_message)}")
        logger.error("[red]✘ FAILED[/red]\n")
        valid_layout = False

    backend_tfvars = tf.account_config_dir / tf.BACKEND_TFVARS
    backend_tfvars = hcl2.loads(backend_tfvars.read_text()) if backend_tfvars.exists() else {}

    logger.info("Checking [bold]backend.tfvars[/bold]:\n")
    names_prefix = f"{tf.project}-{account_name}"
    names_prefix_bootstrap = f"{tf.project}-bootstrap"

    # Check profile, bucket and dynamo table names:
    for field in ("profile", "bucket", "dynamodb_table"):
        logger.info(f"Checking if {field.replace('_', ' ')} starts with {names_prefix}...")
        if backend_tfvars.get(field, "").startswith(names_prefix) or (
            field == "profile" and backend_tfvars.get(field, "").startswith(names_prefix_bootstrap)
        ):
            logger.info("[green]✔ OK[/green]\n")
        else:
            logger.error("[red]✘ FAILED[/red]\n")
            valid_layout = False

    return valid_layout
