import time
import json
import datetime
import webbrowser
from typing import Any, Dict, Tuple

import boto3
import click
from dateutil.tz import tzutc
from configupdater import ConfigUpdater

from leverage import logger
from leverage.path import PathsHandler
from leverage.modules.runner import Runner
from leverage.modules.utils import _handle_subcommand
from leverage.modules.auth import get_sso_access_token
from leverage._utils import get_or_create_section, ExitError
from leverage._internals import pass_state, pass_runner, pass_paths


CONTEXT_SETTINGS = {"ignore_unknown_options": True}


AWS_SSO_LOGIN_URL = "{sso_url}/#/device?user_code={user_code}"


def get_account_roles(sso_client: Any, access_token: str) -> Dict[str, Dict[str, str]]:
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
) -> None:
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


def configure_sso_profiles(paths: PathsHandler) -> None:
    """
    Populate the ~./aws/<project>/config file with the sso profiles from the accounts.
    """
    updater = ConfigUpdater()
    updater.read(paths.aws_config_file)

    # get values from the default profile first
    default_sso_profile_name = f"profile {paths.project}-sso"
    default_profile = updater[default_sso_profile_name]
    region = default_profile["sso_region"].value
    start_url = default_profile["sso_start_url"].value

    # then set a profile for each account
    access_token = get_sso_access_token(paths.sso_token_file)

    logger.info(f"Fetching accounts and roles...")
    client = boto3.client("sso", region_name=region)
    account_roles = get_account_roles(client, access_token)
    for acc_name, values in account_roles.items():
        # account names comes in the form of: {long project name}-{account name}
        short_acc_name = acc_name.replace(paths.project_long + "-", "")
        section_name = f"profile {paths.project}-sso-{short_acc_name}"
        logger.info(f"Adding {section_name}")
        add_sso_profile(updater, section_name, values["role_name"], values["account_id"], region, start_url)

    # save/update the profile file
    updater.update_file()


@click.group(invoke_without_command=True, add_help_option=False, context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@pass_state
@click.pass_context
def aws(context: click.Context, state: Any, args: Tuple[str, ...]) -> None:
    """Run AWS CLI commands in a custom containerized environment."""

    credentials_env_vars = {
        "AWS_SHARED_CREDENTIALS_FILE": str(state.paths.aws_credentials_file),
        "AWS_CONFIG_FILE": str(state.paths.aws_config_file),
    }
    state.runner = Runner(
        binary="aws",
        error_message=(
            f"AWS CLI not found on system. "
            f"Please install it following the instructions at: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
        ),
        env_vars=credentials_env_vars,
    )

    _handle_subcommand(context=context, runner=state.runner, args=args)


@aws.group(invoke_without_command=True, add_help_option=False, context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@pass_runner
@click.pass_context
def configure(context: click.Context, awscli: Runner, args: Tuple[str, ...]) -> None:
    """configure"""
    _handle_subcommand(context=context, runner=awscli, args=args, caller_name="configure")


@configure.command("sso")
@pass_paths
@pass_runner
@click.pass_context
def _sso(context: click.Context, awscli: Runner, paths: PathsHandler) -> None:
    """configure sso"""
    paths.check_for_layer_location()

    # region_primary was added in ref-arch v1
    # for v2 it was replaced by region at project level
    region_primary = "region_primary"
    if "region_primary" not in paths.common_conf:
        region_primary = "region"
    default_region = paths.common_conf.get(region_primary, paths.common_conf.get("sso_region"))
    if default_region is None:
        raise ExitError(1, "No primary region configured in global config file.")

    logger.info("Configuring default profile.")
    default_profile = {"region": default_region, "output": "json"}
    for key, value in default_profile.items():
        awscli.exec("configure", "set", key, value, "--profile", "default")

    if not all(sso_key in paths.common_conf for sso_key in ("sso_start_url", "sso_region")):
        raise ExitError(1, "Missing configuration values for SSO in global config file.")

    sso_role = paths.account_conf.get("sso_role")
    if not sso_role:
        raise ExitError(1, "Missing SSO role in account config file.")

    current_account = paths.account_conf.get("environment")
    try:
        # this is for ref-arch v1
        account_id = paths.common_conf.get("accounts").get(current_account).get("id")
    except AttributeError:
        # this is for ref-arch v2
        try:
            # this is for accounts with no org unit on top of it
            account_id = paths.common_conf.get("organization").get("accounts").get(current_account).get("id")
        except AttributeError:
            try:
                # this is for accounts with no org unit on top of it
                found = False
                for ou in paths.common_conf.get("organization").get("organizational_units"):
                    if current_account in paths.common_conf.get("organization").get("organizational_units").get(ou).get(
                        "accounts"
                    ):
                        account_id = (
                            paths.common_conf.get("organization")
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
                raise ExitError(
                    1, f"Missing account configuration for [bold]{current_account}[/bold] in global config file."
                )
    if not account_id:
        raise ExitError(1, f"Missing id for account [bold]{current_account}[/bold].")

    logger.info(f"Configuring [bold]{paths.project}-sso[/bold] profile.")
    sso_profile = {
        "sso_start_url": paths.common_conf.get("sso_start_url"),
        "sso_region": paths.common_conf.get("sso_region", paths.common_conf.get(region_primary)),
        "sso_account_id": account_id,
        "sso_role_name": sso_role,
    }
    for key, value in sso_profile.items():
        awscli.exec("configure", "set", key, value, "--profile", f"{paths.project}-sso")

    context.invoke(login)

    logger.info("Storing account information.")
    configure_sso_profiles(paths)

    logger.info("SSO profiles configured successfully.")


@aws.group(invoke_without_command=True, add_help_option=False, context_settings=CONTEXT_SETTINGS)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@pass_runner
@click.pass_context
def sso(context: click.Context, awscli: Runner, args: Tuple[str, ...]) -> None:
    """sso"""
    _handle_subcommand(context=context, runner=awscli, args=args, caller_name="sso")


@sso.command()
@pass_paths
@pass_runner
def login(awscli: Runner, paths: PathsHandler) -> None:
    """Login"""
    exit_code, region, _ = awscli.exec("configure", "get", "sso_region", "--profile", f"{paths.project}-sso")
    if exit_code:
        raise ExitError(
            exit_code,
            f"Region configuration for [bold]{paths.project}-sso[/bold] profile not found. \n"
            f"Please run [bold]leverage configure sso[/bold] to configure the SSO profile.",
        )

    paths.sso_cache.mkdir(parents=True, exist_ok=True)

    logger.info(f"Logging in...")
    sso_oidc_client = boto3.client("sso-oidc", region_name=region)

    logger.debug(f"Registering client...")
    sso_oidc_client_creds = sso_oidc_client.register_client(
        clientName=f"leverage-{datetime.datetime.now().timestamp()}",
        clientType="public",
    )
    device_authorization = sso_oidc_client.start_device_authorization(
        clientId=sso_oidc_client_creds["clientId"],
        clientSecret=sso_oidc_client_creds["clientSecret"],
        startUrl=paths.common_conf.get("sso_start_url"),
    )

    logger.info(
        f"Attempting to automatically open the SSO authorization page in your default browser.\n"
        f"If the browser does not open or you wish to use a different device to authorize this request, open the following URL:\n"
        f"\n{paths.common_conf.get('sso_start_url')}\n"
        f"\nThen enter the code:\n"
        f"\n{device_authorization['userCode']}\n"
    )
    webbrowser.open_new_tab(
        f"{paths.common_conf.get('sso_start_url')}/#/device?user_code={device_authorization['userCode']}"
    )

    logger.debug(f"Attempting to create authorization token...")
    _wait_interval = device_authorization["interval"]
    token = None
    while not token:
        try:
            token_response = sso_oidc_client.create_token(
                grantType="urn:ietf:params:oauth:grant-type:device_code",
                deviceCode=device_authorization["deviceCode"],
                clientId=sso_oidc_client_creds["clientId"],
                clientSecret=sso_oidc_client_creds["clientSecret"],
            )

            token_expires_at = datetime.datetime.now(tzutc()) + datetime.timedelta(seconds=token_response["expiresIn"])
            client_expires_at = datetime.datetime.fromtimestamp(sso_oidc_client_creds["clientSecretExpiresAt"], tzutc())

            token = {
                "startUrl": paths.common_conf.get("sso_start_url"),
                "region": region,
                "accessToken": token_response["accessToken"],
                "expiresAt": token_expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "clientId": sso_oidc_client_creds["clientId"],
                "clientSecret": sso_oidc_client_creds["clientSecret"],
                "registrationExpiresAt": client_expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }

        except sso_oidc_client.exceptions.SlowDownException:
            # Polling too frequently.
            time.sleep(_wait_interval + 5)
        except sso_oidc_client.exceptions.AuthorizationPendingException:
            # User hasn't finished logging in.
            time.sleep(_wait_interval)
        except Exception as e:
            raise ExitError(
                1, f"An error occurred while polling for authorization token: {e}\n" f"Aborting login process."
            )

    logger.debug(f"Token expires at: {token['expiresAt']}")
    logger.debug(f"Caching token.")
    token_file = paths.sso_cache / "token"
    token_file.write_text(json.dumps(token))

    logger.info(f"Successfully logged in!.")


@sso.command()
@pass_paths
def logout(paths: PathsHandler) -> None:
    """Logout"""
    region = paths.common_conf.get("sso_region")
    sso_client = boto3.client("sso", region_name=region)

    logger.debug("Logging out of AWS SSO...")
    sso_client.logout(accessToken=get_sso_access_token(paths.sso_token_file))

    logger.debug("Removing SSO Tokens...")
    if paths.sso_cache.exists():
        for file in paths.sso_cache.glob("*"):
            file.unlink()

    logger.debug("Wiping current SSO credentials...")
    updater = ConfigUpdater()
    updater.read(paths.aws_credentials_file)

    sections = updater.sections()
    for section in sections:
        if section not in ("default", f"{paths.project}-sso"):
            updater.remove_section(section)
    updater.update_file()

    paths.aws_credentials_file.unlink(missing_ok=True)

    logger.debug("All SSO credentials wiped!.")

    logger.info(
        f"Don't forget to log out of your [bold]AWS SSO[/bold] start page {paths.common_conf.get('sso_start_url')}"
        f" and your external identity provider portal."
    )
