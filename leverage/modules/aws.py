import boto3
import click
from click.exceptions import Exit
from configupdater import ConfigUpdater

from leverage import logger
from leverage._internals import pass_state
from leverage._internals import pass_container
from leverage._utils import get_or_create_section
from leverage.container import get_docker_client, SSOContainer
from leverage.container import AWSCLIContainer
from leverage.modules.utils import _handle_subcommand

CONTEXT_SETTINGS = {"ignore_unknown_options": True}


def get_account_roles(sso_client, access_token: str) -> dict:
    """
    Fetch the accounts and roles from the user.
    """
    account_roles = {}

    accounts = sso_client.list_accounts(accessToken=access_token)
    for account in accounts["accountList"]:
        acc_role = sso_client.list_account_roles(
            accessToken=access_token,
            accountId=account["accountId"],
            maxResults=1,  # assume the first role is always the correct one
        )["roleList"][0]

        account_roles[account["accountName"]] = {
            "account_id": account["accountId"],
            "role_name": acc_role["roleName"],
        }

    return account_roles


def add_sso_profile(
    config_updater: ConfigUpdater, section_name: str, role_name: str, account_id: str, region: str, start_url: str
):
    """
    Add a profile to the config file.
    """
    section = get_or_create_section(config_updater, section_name)

    data = {
        "role_name": role_name,
        "account_id": account_id,
        "sso_region": region,
        "sso_start_url": start_url,
    }
    for k, v in data.items():
        # can't set a dict directly, so we need to go field by field
        section[k] = v


def configure_sso_profiles(cli: SSOContainer):
    """
    Populate the ~./aws/<project>/config file with the sso profiles from the accounts.
    """
    updater = ConfigUpdater()
    updater.read(cli.paths.host_aws_profiles_file)

    # get values from the default profile first
    default_sso_profile_name = f"profile {cli.project}-sso"
    default_profile = updater[default_sso_profile_name]
    region = default_profile["sso_region"].value
    start_url = default_profile["sso_start_url"].value

    # then set a profile for each account
    access_token = cli.get_sso_access_token()
    logger.info(f"Fetching accounts and roles...")
    client = boto3.client("sso", region_name=region)
    account_roles = get_account_roles(client, access_token)
    for acc_name, values in account_roles.items():
        # account names comes in the form of: {long project name}-{account name}
        short_acc_name = acc_name.replace(cli.paths.project_long + "-", "")
        section_name = f"profile {cli.project}-sso-{short_acc_name}"
        logger.info(f"Adding {section_name}")
        add_sso_profile(updater, section_name, values["role_name"], values["account_id"], region, start_url)

    # save/update the profile file
    updater.update_file()


@click.group(invoke_without_command=True, add_help_option=False, context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@pass_state
@click.pass_context
def aws(context, state, args):
    """Run AWS CLI commands in a custom containerized environment."""
    cli = AWSCLIContainer(get_docker_client())
    state.container = cli
    state.container.ensure_image()

    _handle_subcommand(context=context, cli_container=cli, args=args)


@aws.group(invoke_without_command=True, add_help_option=False, context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@pass_container
@click.pass_context
def configure(context, cli, args):
    """configure"""
    _handle_subcommand(context=context, cli_container=cli, args=args, caller_name="configure")


@configure.command("sso")
@pass_container
@click.pass_context
def _sso(context, cli):
    """configure sso"""
    cli.paths.check_for_layer_location()

    # region_primary was added in refarch v1
    # for v2 it was replaced by region at project level
    region_primary = "region_primary"
    if "region_primary" not in cli.paths.common_conf:
        region_primary = "region"
    default_region = cli.paths.common_conf.get(region_primary, cli.paths.common_conf.get("sso_region"))
    if default_region is None:
        logger.error("No primary region configured in global config file.")
        raise Exit(1)

    logger.info("Configuring default profile.")
    default_profile = {"region": default_region, "output": "json"}
    for key, value in default_profile.items():
        cli.exec(f"configure set {key} {value}", profile="default")

    if not all(sso_key in cli.paths.common_conf for sso_key in ("sso_start_url", "sso_region")):
        logger.error("Missing configuration values for SSO in global config file.")
        raise Exit(1)

    sso_role = cli.paths.account_conf.get("sso_role")
    if not sso_role:
        logger.error("Missing SSO role in account config file.")
        raise Exit(1)

    current_account = cli.paths.account_conf.get("environment")
    try:
        # this is for refarch v1
        account_id = cli.paths.common_conf.get("accounts").get(current_account).get("id")
    except AttributeError:
        # this is for refarch v2
        try:
            # this is for accounts with no org unit on top of it
            account_id = cli.paths.common_conf.get("organization").get("accounts").get(current_account).get("id")
        except AttributeError:
            try:
                # this is for accounts with no org unit on top of it
                found = False
                for ou in cli.paths.common_conf.get("organization").get("organizational_units"):
                    if current_account in cli.paths.common_conf.get("organization").get("organizational_units").get(
                        ou
                    ).get("accounts"):
                        account_id = (
                            cli.paths.common_conf.get("organization")
                            .get("organizational_units")
                            .get(ou)
                            .get("accounts")
                            .get(current_account)
                            .get("id")
                        )
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
        "sso_start_url": cli.paths.common_conf.get("sso_start_url"),
        "sso_region": cli.paths.common_conf.get("sso_region", cli.paths.common_conf.get(region_primary)),
        "sso_account_id": account_id,
        "sso_role_name": sso_role,
    }
    for key, value in sso_profile.items():
        cli.exec(f"configure set {key} {value}", profile=f"{cli.project}-sso")

    context.invoke(login)

    logger.info("Storing account information.")
    configure_sso_profiles(cli)


@aws.group(invoke_without_command=True, add_help_option=False, context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@pass_container
@click.pass_context
def sso(context, cli, args):
    """sso"""
    _handle_subcommand(context=context, cli_container=cli, args=args, caller_name="sso")


@sso.command()
@pass_container
def login(cli):
    """Login"""
    exit_code, region = cli.exec(f"configure get sso_region --profile {cli.project}-sso")
    if exit_code:
        logger.error(f"Region configuration for [bold]{cli.project}-sso[/bold] profile not found.")
        raise Exit(1)

    if exit_code := cli.sso_login():
        raise Exit(exit_code)


@sso.command()
@pass_container
def logout(cli):
    """Logout"""
    exit_code = cli.system_start(cli.AWS_SSO_LOGOUT_SCRIPT)
    if exit_code:
        raise Exit(exit_code)

    logger.info(
        f"Don't forget to log out of your [bold]AWS SSO[/bold] start page {cli.paths.common_conf.get('sso_start_url')}"
        " and your external identity provider portal."
    )
