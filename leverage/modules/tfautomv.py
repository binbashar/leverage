import click
from click.exceptions import Exit

from leverage._internals import pass_state
from leverage.modules.runner import Runner
from leverage.modules.tf import tf_default_args
from leverage.modules.auth import check_sso_token, refresh_layer_credentials


@click.command()
@click.argument("args", nargs=-1)
@pass_state
def tfautomv(state, args):
    """Run TFAutomv commands in the context of the current project.`"""
    tf_default_args_string = " ".join(tf_default_args())
    credentials_env_vars = {
        "AWS_SHARED_CREDENTIALS_FILE": str(state.paths.aws_credentials_file),
        "AWS_CONFIG_FILE": str(state.paths.aws_config_file),
        "TF_CLI_ARGS_init": tf_default_args_string,
        "TF_CLI_ARGS_plan": tf_default_args_string,
    }
    state.runner = Runner(
        binary="tfautomv",
        error_message=(
            f"TFAutomv not found on system. "
            f"Please install it following the instructions at: https://github.com/busser/tfautomv?tab=readme-ov-file#installation"
        ),
        env_vars=credentials_env_vars,
    )

    tf_binary = "tofu" if not state.paths.tf_binary else state.paths.tf_binary
    filtered_args = (
        arg
        for index, arg in list(enumerate(args))
        if not str(arg).startswith("--terraform-bin") or not arg[index - 1] == "--terraform-bin"
    )
    tfautomv_args = (*filtered_args, f"--terraform-bin={tf_binary}")

    check_sso_token(state.paths)
    refresh_layer_credentials(state.paths)

    if exit_code := state.runner.run(*tfautomv_args):
        raise Exit(exit_code)
