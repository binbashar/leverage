from typing import Optional, Tuple, Callable

from click.exceptions import Exit
from click.core import Context

from leverage.modules.runner import Runner


def _handle_subcommand(
    context: Context,
    runner: Runner,
    args: Tuple[str, ...],
    caller_name: Optional[str] = None,
    pre_invocation_callback: Optional[Callable] = None,
) -> None:
    """Decide if command corresponds to a wrapped one or not and run accordingly.

    Args:
        context (click.context): Current context
        runner (Runner): Runner where commands will be executed
        args (tuple(str)): Arguments received by Leverage
        caller_name (str, optional): Calling command. Defaults to None.
        pre_invocation_callback (Callable, optional): Callback to be called before the invocation. Defaults to None.
    Raises:
        Exit: Whenever runner execution returns a non-zero exit code
    """
    caller_pos = args.index(caller_name) if caller_name is not None else 0

    # Find if one of the wrapped subcommand was invoked
    wrapped_subcommands = context.command.commands.keys()
    subcommand = next((arg for arg in args[caller_pos:] if arg in wrapped_subcommands), None)

    if subcommand is None:
        # Run the command directly
        if pre_invocation_callback:
            pre_invocation_callback()
        exit_code = runner.run(*args)
        raise Exit(exit_code)

    subcommand = context.command.commands.get(subcommand)
    # Check that the subcommand arguments are valid
    subcommand.make_context(
        info_name=subcommand.name, args=list(args)[args.index(subcommand.name) + 1 :], parent=context
    )
    # Invoke wrapped command
    if not subcommand.params:
        context.invoke(subcommand)
    else:
        context.forward(subcommand)
