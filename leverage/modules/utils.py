import click
from click.exceptions import Exit


def _handle_subcommand(context, cli_container, args, caller_name=None):
    """Decide if command corresponds to a wrapped one or not and run accordingly.

    Args:
        context (click.context): Current context
        cli_container (LeverageContainer): Container where commands will be executed
        args (tuple(str)): Arguments received by Leverage
        caller_name (str, optional): Calling command. Defaults to None.

    Raises:
        Exit: Whenever container execution returns a non-zero exit code
    """
    caller_pos = args.index(caller_name) if caller_name is not None else 0

    # Find if one of the wrapped subcommand was invoked
    wrapped_subcommands = context.command.commands.keys()
    subcommand = next((arg for arg in args[caller_pos:] if arg in wrapped_subcommands), None)

    if subcommand is None:
        # Pass command to the container directly
        exit_code = cli_container.start(" ".join(args))
        if not exit_code:
            raise Exit(exit_code)

    else:
        # Invoke wrapped command
        subcommand = context.command.commands.get(subcommand)
        if not subcommand.params:
            context.invoke(subcommand)
        else:
            context.forward(subcommand)


mount_option = click.option("--mount", multiple=True, type=click.Tuple([str, str]))
env_var_option = click.option("--env-var", multiple=True, type=click.Tuple([str, str]))
auth_mfa = click.option(
    "--mfa", is_flag=True, default=False, help="Enable Multi Factor Authentication upon launching shell."
)
auth_sso = click.option("--sso", is_flag=True, default=False, help="Enable SSO Authentication upon launching shell.")
