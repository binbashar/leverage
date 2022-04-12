import webbrowser

import click
from click.exceptions import Exit

from leverage import logger
from leverage._internals import pass_state
from leverage._internals import pass_container
from leverage.container import get_docker_client
from leverage.container import AWSCLIContainer


CONTEXT_SETTINGS={"ignore_unknown_options": True}


@click.group(invoke_without_command=True, context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@pass_state
@click.pass_context
def aws(context, state, args):
    """ Run AWS CLI commands in a custom containerized environment. """
    cli = AWSCLIContainer(get_docker_client())
    state.container = cli
    state.container.ensure_image()

    if not args:
        click.echo(context.get_help())
        return

    # Find if one of the hijacked commands was invoked
    index = None
    for command in context.command.commands.keys():
        if command in args:
            index = args.index(command)
            break

    if index is None:
        exit_code = cli.start(" ".join(list(args)))
        if not exit_code:
            raise Exit(exit_code)
        return

    # Invoke hijacked command
    command = context.command.commands.get(args[index])
    context.invoke(command, args=(*args[index+1:], *args[:index]))


@aws.group(invoke_without_command=True, context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@pass_container
@click.pass_context
def configure(context, cli, args):
    """ configure """
    if not args:
        click.echo(context.get_help())
        return

    command = context.command.commands.get(args[0])
    if command is not None:
        context.invoke(command)
        return

    exit_code = cli.start(" ".join(["configure"] + list(args)))
    if not exit_code:
        raise Exit(exit_code)


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

    default_region = cli.common_conf.get("region_primary", cli.common_conf.get("sso_region"))
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
        account_id = cli.common_conf.get("accounts").get(current_account).get("id")
    except AttributeError:
        logger.error("Missing environment configuration in global config file.")
        raise Exit(1)
    if not account_id:
        logger.error(f"Missing id for account [bold]{current_account}[/bold].")
        raise Exit(1)

    logger.info(f"Configuring [bold]{cli.project}-sso[/bold] profile.")
    sso_profile = {
        "sso_start_url": cli.common_conf.get("sso_start_url"),
        "sso_region": cli.common_conf.get("sso_region", cli.common_conf.get("region_primary")),
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


@aws.group(invoke_without_command=True, context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@pass_container
@click.pass_context
def sso(context, cli, args):
    """ SSO """
    if not args:
        click.echo(context.get_help())
        return

    command = context.command.commands.get(args[0])
    if command is not None:
        context.invoke(command)
        return

    exit_code = cli.start(" ".join(["sso"] + list(args)))
    if not exit_code:
        raise Exit(exit_code)


@sso.command()
@pass_container
def login(cli):
    """ Login """
    if (cli.cwd in (cli.root_dir, cli.account_dir) or
        cli.account_dir.parent != cli.root_dir or
        not list(cli.cwd.glob("*.tf"))):
        logger.error("SSO configuration can only be performed at [bold]layer[/bold] level.")
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
