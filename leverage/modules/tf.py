import re
from pathlib import Path
from typing import Sequence, List

import click
from click.exceptions import Exit

from leverage import logger
from leverage.path import PathsHandler
from leverage.modules.tfrunner import TFRunner
from leverage._utils import ExitError, parse_tf_file
from leverage._internals import pass_paths, pass_runner, pass_state
from leverage._backend_config import get_backend_key, set_backend_key
from leverage.modules.auth import refresh_layer_credentials, check_sso_token

REGION = rf"(global|([a-z]{2}(-gov)?)-(central|(north|south)?(east|west)?)-\d)"


# ###########################################################################
# CREATE THE TOFU AND TERRAFORM GROUPS
# ###########################################################################
@click.group()
@pass_state
def tofu(state):
    """Run OpenTofu commands in a custom containerized environment that provides extra functionality when interacting
    with your cloud provider such as handling multi factor authentication for you.
    All tofu subcommands that receive extra args will pass the given strings as is to their corresponding OpenTofu
    counterparts in the container. For example as in `leverage tofu apply -auto-approve` or
    `leverage tofu init -reconfigure`
    """
    credentials_env_vars = {
        "AWS_SHARED_CREDENTIALS_FILE": str(state.paths.aws_credentials_file),
        "AWS_CONFIG_FILE": str(state.paths.aws_config_file),
    }
    state.runner = TFRunner(env_vars=credentials_env_vars)


@click.group()
@pass_state
def terraform(state):
    """Run Terraform commands in a custom containerized environment that provides extra functionality when interacting
    with your cloud provider such as handling multi factor authentication for you.
    All terraform subcommands that receive extra args will pass the given strings as is to their corresponding Terraform
    counterparts in the container. For example as in `leverage terraform apply -auto-approve` or
    `leverage terraform init -reconfigure`
    """
    credentials_env_vars = {
        "AWS_SHARED_CREDENTIALS_FILE": str(state.paths.aws_credentials_file),
        "AWS_CONFIG_FILE": str(state.paths.aws_config_file),
    }
    state.runner = TFRunner(terraform=True, env_vars=credentials_env_vars)


CONTEXT_SETTINGS = {"ignore_unknown_options": True}

# ###########################################################################
# CREATE THE TF GROUP'S COMMANDS
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


@click.command(context_settings=CONTEXT_SETTINGS)
@click.option("--skip-validation", is_flag=True, help="Skip layout validation.")
@layers_option
@click.argument("args", nargs=-1)
@pass_runner
def init(tf: TFRunner, args: Sequence[str], layers: str, skip_validation: bool):
    """Initialize this layer."""
    invoke_for_all_commands(layers, _init, *args, skip_validation=skip_validation)


@click.command(context_settings=CONTEXT_SETTINGS)
@layers_option
@click.argument("args", nargs=-1)
@pass_runner
def plan(tf: TFRunner, args: Sequence[str], layers: str):
    """Generate an execution plan for this layer."""
    invoke_for_all_commands(layers, _plan, *args)


@click.command(context_settings=CONTEXT_SETTINGS)
@layers_option
@click.argument("args", nargs=-1)
@pass_runner
def apply(tf: TFRunner, args: Sequence[str], layers: str):
    """Build or change the infrastructure in this layer."""
    invoke_for_all_commands(layers, _apply, *args)


@click.command(context_settings=CONTEXT_SETTINGS)
@layers_option
@click.argument("args", nargs=-1)
@pass_runner
def output(tf: TFRunner, args: Sequence[str], layers: str):
    """Show all output variables of this layer."""
    invoke_for_all_commands(layers, _output, *args)


@click.command(context_settings=CONTEXT_SETTINGS)
@layers_option
@click.argument("args", nargs=-1)
@pass_runner
def destroy(tf: TFRunner, args: Sequence[str], layers: str):
    """Destroy infrastructure in this layer."""
    invoke_for_all_commands(layers, _destroy, *args)


@pass_paths
def tf_default_args(paths: PathsHandler) -> tuple:
    """
        Returns a tuple of strings containing all valid config files for layer as
        parameters for OpenTofu/Terraform.

    Args:
        paths: PathsHandler object

    Returns:
        tuple: Tuple of strings containing all valid config files for layer as
        parameters for OpenTofu/Terraform.
    """
    common_config_files = tuple(
        f"-var-file={common_file.as_posix()}" for common_file in paths.common_config_dir.glob("*.tfvars")
    )
    account_config_files = tuple(
        f"-var-file={account_file.as_posix()}" for account_file in paths.account_config_dir.glob("*.tfvars")
    )
    return common_config_files + account_config_files


@click.command()
@pass_runner
def version(tf):
    """Print version."""
    tf.run("version")


@click.command("format", context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1)
@pass_runner
def _format(tf, args):
    """Check if all files meet the canonical format and rewrite them accordingly."""
    args = args if "-recursive" in args else (*args, "-recursive")
    tf.run("fmt", *args)


@click.command("force-unlock")
@click.argument("lock_id", metavar="LOCK_ID")
@pass_paths
@pass_runner
def force_unlock(tf, paths: PathsHandler, lock_id):
    """Force unlock the state file."""
    check_sso_token(paths)
    refresh_layer_credentials(paths)
    if exit_code := tf.run("force-unlock", *tf_default_args(), lock_id):
        raise Exit(exit_code)


@click.command()
@pass_paths
@pass_runner
def validate(tf, paths: PathsHandler):
    """Validate code of the current directory. Previous initialization might be needed."""
    check_sso_token(paths)
    refresh_layer_credentials(paths)
    if exit_code := tf.run("validate", *tf_default_args()):
        raise Exit(exit_code)


@click.command("validate-layout")
@pass_paths
def validate_layout(paths):
    """Validate layer conforms to Leverage convention."""
    return _validate_layout(paths.cwd)


@click.command("import")
@click.argument("address")
@click.argument("_id", metavar="ID")
@pass_runner
def _import(tf, address, _id):
    """Import a resource."""
    if exit_code := tf.run("import", *tf_default_args(), address, _id):
        raise Exit(exit_code)


@click.command("refresh-credentials")
@pass_paths
def refresh_credentials(paths):
    """Refresh the AWS credentials used on the current layer."""
    paths.check_for_layer_location()
    check_sso_token(paths)
    refresh_layer_credentials(paths)


# ###########################################################################
# ATTACH SUBCOMMANDS TO TF COMMANDS
# ###########################################################################

for subcommand in (
    init,
    plan,
    apply,
    output,
    destroy,
    version,
    _format,
    force_unlock,
    validate,
    validate_layout,
    _import,
    refresh_credentials,
):
    tofu.add_command(subcommand)
    terraform.add_command(subcommand)


# ###########################################################################
# HANDLER FOR MANAGING THE BASE COMMANDS (init, plan, apply, destroy, output)
# ###########################################################################
@pass_paths
def invoke_for_all_commands(paths, layers, command, *args: Sequence[str], skip_validation=True):
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
    location_type = paths.get_location_type()
    if location_type == "layer" and len(layers) == 0:
        # running on a layer
        layers = [paths.cwd]
    elif location_type == "layer":
        # running on a layer but --layers was set
        raise ExitError(1, "Can not set [bold]--layers[/bold] inside a layer.")
    elif location_type in ["account", "layers-group"] and len(layers) == 0:
        # running on an account but --layers was not set
        raise ExitError(1, "[bold]--layers[/bold] has to be set.")
    elif location_type not in ["account", "layer", "layers-group"]:
        # running outside a layer and account
        raise ExitError(1, "This command has to be run inside a layer or account directory.")
    else:
        # running on an account with --layers set
        layers = [paths.cwd / x for x in layers]

    # validate each layer before calling the execute command
    for layer in layers:
        logger.debug(f"Checking for layer {layer}...")

        # check layers existence
        if not layer.is_dir():
            raise ExitError(1, f"Directory [red]{layer}[/red] does not exist or is not a directory\n")

        # validate layer
        validate_for_all_commands(layer, skip_validation=skip_validation)

        # set the s3 key
        if not get_backend_key(layer / "config.tf"):
            backend_key_base = f"{paths.cwd.relative_to(paths.root_dir).as_posix()}/terraform.tfstate"
            backend_key = backend_key_base.replace("/base-", "/").replace("/tools-", "/")
            set_backend_key(layer / "config.tf", backend_key)

    # check layers existence
    for layer in layers:
        if len(layers) > 1:
            logger.info(f"Invoking command for layer {layer}...")

        # execute the actual command
        command(args, working_dir=layer)

    return layers


def validate_for_all_commands(layer, skip_validation=False):
    """
    Validate existence of layer and, if set, all the Leverage related stuff
    of each of them

    Args:
        layer: a full layer directory
    """
    logger.debug(f"Checking layer {layer}...")
    if not skip_validation and not _validate_layout(layer):
        raise ExitError(
            1,
            "Layer configuration doesn't seem to be valid. Exiting.\n"
            "If you are sure your configuration is actually correct "
            "you may skip this validation using the --skip-validation flag.",
        )


# ###########################################################################
# BASE COMMAND EXECUTORS
# ###########################################################################
@pass_paths
@pass_runner
def _init(tf: TFRunner, paths: PathsHandler, args: Sequence[str], working_dir: Path):
    """Initialize this layer."""

    filtered_args = (
        arg
        for index, arg in list(enumerate(args))
        if not str(arg).startswith("-backend-config") or not arg[index - 1] == "-backend-config"
    )
    init_args = (*filtered_args, f"-backend-config={paths.backend_tfvars}")

    check_sso_token(paths)
    refresh_layer_credentials(paths)

    if exit_code := tf.run("init", *init_args, working_dir=working_dir):
        raise Exit(exit_code)


@pass_paths
@pass_runner
def _plan(tf: TFRunner, paths: PathsHandler, args: Sequence[str], working_dir: Path):
    """Generate an execution plan for this layer."""
    check_sso_token(paths)
    refresh_layer_credentials(paths)

    if exit_code := tf.run("plan", *tf_default_args(), *args, working_dir=working_dir):
        raise Exit(exit_code)


def has_a_plan_file(args: Sequence[str]) -> bool:
    """Determine whether the list of arguments has a plan file at the end.

    OpenTofu/Terraform apply arguments have the form "-target ADDRESS" or
    "-target=ADDRESS" in one case "-var 'NAME=value'" or "-var='NAME=value'".
    There are also flags with the form "-flag".
    We just need to know if there is or not a plan file as a last argument to
    decide if we prepend our default terraform arguments or not.

    Cases to consider:
     Args                                | Plan file present
    -------------------------------------|-------------------
     ()                                  | False
     ("-flag")                           | False
     ("-var=value")                      | False
     ("plan_file")                       | True
     (..., "-var", "value")              | False
     (..., "-flag", "plan_file")         | True
     (..., "-var=value", "plan_file")    | True
     (..., "-var", "value", "plan_file") | True

    """

    # Valid 'apply' flags:
    # https://developer.hashicorp.com/terraform/cli/commands/apply
    # https://opentofu.org/docs/cli/commands/apply
    tf_flags = [
        # OpenTofu/Terraform flags:
        "-destroy",
        "-refresh-only",
        "-detailed-exitcode",
        "-auto-approve",
        "-compact-warnings",
        "-json",
        "-no-color",
        # OpenTofu exclusive flags:
        "-consolidate-warnings",
        "-consolidate-errors",
        "-concise",
        "-show-sensitive",
    ]

    if not args or args[-1].startswith("-"):
        return False

    if len(args) > 1:
        second_last = args[-2]
        if second_last.startswith("-"):
            if not "=" in second_last and second_last not in tf_flags:
                return False

    return True


@pass_paths
@pass_runner
def _apply(tf: TFRunner, paths: PathsHandler, args: Sequence[str], working_dir: Path):
    """Build or change the infrastructure in this layer."""
    default_args = () if has_a_plan_file(args) else tf_default_args()
    logger.debug(f"Default args passed to apply command: {default_args}")

    check_sso_token(paths)
    refresh_layer_credentials(paths)

    if exit_code := tf.run("apply", *default_args, *args, working_dir=working_dir):
        raise Exit(exit_code)


@pass_paths
@pass_runner
def _output(tf: TFRunner, paths: PathsHandler, args: Sequence[str], working_dir: Path):
    """Show all output variables of this layer."""
    check_sso_token(paths)
    refresh_layer_credentials(paths)

    if exit_code := tf.run("output", *args, working_dir=working_dir):
        raise Exit(exit_code)


@pass_paths
@pass_runner
def _destroy(tf: TFRunner, paths: PathsHandler, args: Sequence[str], working_dir: Path):
    """Destroy infrastructure in this layer."""
    check_sso_token(paths)
    refresh_layer_credentials(paths)

    if exit_code := tf.run("destroy", *tf_default_args(), *args, working_dir=working_dir):
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
        list of strings: Backend bucket key parts
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
        resp.append(f"{'/'.join([account_name, *layer_path])}/terraform.tfstate")

    return resp


@pass_paths
def _validate_layout(paths, layer: str):
    paths.check_for_layer_location()

    # Check for `environment = <account name>` in account.tfvars
    account_name = paths.account_conf.get("environment")
    logger.info("Checking environment name definition in [bold]account.tfvars[/bold]...")
    if account_name is None:
        raise ExitError(1, "[red]✘ FAILED[/red]\n")
    logger.info("[green]✔ OK[/green]\n")

    # Check if account directory name matches with environment name
    if paths.account_dir.stem != account_name:
        logger.warning(
            "[yellow]‼[/yellow] Account directory name does not match environment name.\n"
            f"  Expected [bold]{account_name}[/bold], found [bold]{paths.account_dir.stem}[/bold]\n"
        )

    # Flag to report layout validity
    valid_layout = True

    # Check backend bucket key
    if backend_key := get_backend_key(Path(layer) / "config.tf"):
        expected_backend_keys = _make_layer_backend_key(Path(layer), paths.account_dir, account_name)
        logger.info("Checking backend key...")
        logger.info(f"Found: '{backend_key}'")

        if backend_key in expected_backend_keys:
            logger.info("[green]✔ OK[/green]\n")
        else:
            logger.info(f"Expected one of: {'; '.join(expected_backend_keys)}")
            logger.error("[red]✘ FAILED[/red]\n")
            valid_layout = False
    else:
        logger.info("No backend key found. Skipping backend key validation.\n")

    backend_tfvars = parse_tf_file(paths.backend_tfvars) if paths.backend_tfvars.exists() else {}

    logger.info("Checking [bold]backend.tfvars[/bold]:\n")
    names_prefix = f"{paths.project}-{account_name}"
    names_prefix_bootstrap = f"{paths.project}-bootstrap"

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
