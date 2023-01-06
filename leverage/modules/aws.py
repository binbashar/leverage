import webbrowser

import click
from click.exceptions import Exit

from leverage import logger
from leverage._internals import pass_state
from leverage._internals import pass_container
from leverage.container import get_docker_client
from leverage.container import AWSCLIContainer


def _handle_subcommand(context, cli_container, args, caller_name=None):
    """ Decide if command corresponds to a wrapped one or not and run accordingly.

    Args:
        context (click.context): Current context
        cli_container (AWSCLIContainer): Container where commands will be executed
        args (tuple(str)): Arguments received by Leverage
        caller_name (str, optional): Calling command. Defaults to None.

    Raises:
        Exit: Whenever container execution returns a non zero exit code
    """
    caller_pos = args.index(caller_name) if caller_name is not None else 0

    # Find if one of the wrapped subcommand was invoked
    wrapped_subcommands = context.command.commands.keys()
    subcommand = next((arg
                       for arg in args[caller_pos:]
                       if arg in wrapped_subcommands), None)

    if subcommand is None:
        # Pass command to aws cli directly
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


CONTEXT_SETTINGS={
    "ignore_unknown_options": True
}


@click.group(invoke_without_command=True,
             add_help_option=False,
             context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@pass_state
@click.pass_context
def aws(context, state, args):
    """ Run AWS CLI commands in a custom containerized environment. """
    cli = AWSCLIContainer(get_docker_client())
    state.container = cli
    state.container.ensure_image()

    _handle_subcommand(context=context, cli_container=cli, args=args)


@aws.group(invoke_without_command=True,
           add_help_option=False,
           context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@pass_container
@click.pass_context
def configure(context, cli, args):
    """ configure """
    _handle_subcommand(context=context, cli_container=cli, args=args, caller_name="configure")


@configure.command("sso")
@pass_container
@click.pass_context
def _sso(context, cli):
    """ configure sso """
    if (cli.cwd in (cli.root_dir, cli.account_dir) or
        cli.account_dir.parent != cli.root_dir or
        not list(cli.cwd.glob("*.tf"))):
        logger.error("SSO configuration can only be performed at [bold]layer[/bold] level.")
        raise Exit(1)

    # region_primary was added in refarch v1
    # for v2 it was replaced by region at project level
    region_primary = 'region_primary'
    if not 'region_primary' in cli.common_conf:
        region_primary = 'region'
    default_region = cli.common_conf.get(region_primary, cli.common_conf.get("sso_region"))
    if default_region is None:
        logger.error("No primary region configured in global config file.")
        raise Exit(1)

    logger.info("Configuring default profile.")
    default_profile = {
        "region": default_region,
        "output": "json"
    }
    for key, value in default_profile.items():
        cli.exec(f"configure set {key} {value}", profile="default")

    if not all(sso_key in cli.common_conf for sso_key in ("sso_start_url", "sso_region")):
        logger.error("Missing configuration values for SSO in global config file.")
        raise Exit(1)

    sso_role = cli.account_conf.get("sso_role")
    if not sso_role:
        logger.error("Missing SSO role in account config file.")
        raise Exit(1)

    current_account = cli.account_conf.get("environment")
    try:
        # this is for refarch v1
        account_id = cli.common_conf.get("accounts").get(current_account).get("id")
    except AttributeError:
        # this is for refarch v2
        try:
            # this is for accounts with no org unit on top of it
            account_id = cli.common_conf.get("organization").get("accounts").get(current_account).get("id")
        except AttributeError:
            try:
                # this is for accounts with no org unit on top of it
                found = False
                for ou in cli.common_conf.get("organization").get("organizational_units"):
                    if current_account in cli.common_conf.get("organization").get("organizational_units").get(ou).get("accounts"):
                        account_id = cli.common_conf.get("organization").get("organizational_units").get(ou).get("accounts").get(current_account).get("id")
                        found = True
                        break
                if not found:
                    raise AttributeError
            except AttributeError:
                logger.error(f"Missing account configuration for [bold]{current_account}[/bold] in global config file.")
                raise Exit(1)
    if not account_id:
        logger.error(f"Missing id for account [bold]{current_account}[/bold].")
        raise Exit(1)

    logger.info(f"Configuring [bold]{cli.project}-sso[/bold] profile.")
    sso_profile = {
        "sso_start_url": cli.common_conf.get("sso_start_url"),
        "sso_region": cli.common_conf.get("sso_region", cli.common_conf.get(region_primary)),
        "sso_account_id": account_id,
        "sso_role_name": sso_role
    }
    for key, value in sso_profile.items():
        cli.exec(f"configure set {key} {value}", profile=f"{cli.project}-sso")

    context.invoke(login)

    logger.info("Storing account information.")
    exit_code = cli.system_start(cli.AWS_SSO_CONFIGURE_SCRIPT)
    if exit_code:
        raise Exit(exit_code)


@aws.group(invoke_without_command=True,
           add_help_option=False,
           context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@pass_container
@click.pass_context
def sso(context, cli, args):
    """ sso """
    _handle_subcommand(context=context, cli_container=cli, args=args, caller_name="sso")


@sso.command()
@pass_container
def login(cli):
    """ Login """
    # only from account or layer directories
    # when to fail:
    # - when this cond meets:
    #   - no account dir
    #   - no layer dir
    if not cli.get_location_type() in ['account', 'layer', 'layers-group']:
        logger.error("SSO configuration can only be performed at [bold]layer[/bold] or [bold]account[/bold] level.")
        raise Exit(1)

    exit_code, region = cli.exec(f"configure get sso_region --profile {cli.project}-sso")
    if exit_code:
        logger.error(f"Region configuration for [bold]{cli.project}-sso[/bold] profile not found.")
        raise Exit(1)

    webbrowser.open_new_tab(cli.SSO_LOGIN_URL.format(region=region.strip()))
    exit_code = cli.system_start(cli.AWS_SSO_LOGIN_SCRIPT)
    if exit_code:
        raise Exit(exit_code)


@sso.command()
@pass_container
def logout(cli):
    """ Logout """
    exit_code = cli.system_start(cli.AWS_SSO_LOGOUT_SCRIPT)
    if exit_code:
        raise Exit(exit_code)

    logger.info(f"Don't forget to log out of your [bold]AWS SSO[/bold] start page {cli.common_conf.get('sso_start_url')}"
                " and your external identity provider portal.")
