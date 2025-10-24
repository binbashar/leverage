import time
import json
from pathlib import Path
from datetime import datetime
from dateutil.tz import tzutc
from configparser import NoSectionError, NoOptionError

import boto3
from botocore.exceptions import ClientError
from configupdater import ConfigUpdater

from leverage import logger
from leverage.path import PathsHandler
from leverage._utils import key_finder, ExitError, get_or_create_section, parse_tf_file


class SkipProfile(Exception):
    pass


def get_layer_profile(raw_profile: str, config_updater: ConfigUpdater, tf_profile: str, project: str):
    if "local." in raw_profile:
        # ignore values referencing to local variables
        # we will search for profiles directly in locals.tf instead
        raise SkipProfile

    # if it is exactly that variable, we already know the layer profile is tf_profile
    layer_profile = tf_profile if raw_profile in ("${var.profile}", "each.value.profile") else None

    # replace variables with their corresponding values
    raw = (
        raw_profile.replace("${var.profile}", tf_profile)
        .replace("${var.project}", project)
        .replace("each.value.profile", tf_profile)
    )

    # the project and the role are at the beginning and end of the string
    _, *account_name, _ = raw.split("-")
    account_name = "-".join(account_name)
    logger.info(f"Attempting to get temporary credentials for {account_name} account.")

    sso_profile = f"{project}-sso-{account_name}"
    # if profile wasn't configured during configuration step
    # it means we do not have permissions for the role in the account
    try:
        account_id = config_updater.get(f"profile {sso_profile}", "account_id").value
        sso_role = config_updater.get(f"profile {sso_profile}", "role_name").value
    except NoSectionError:
        raise ExitError(40, f"Missing {sso_profile} permission for account {account_name}.")

    # if we are processing a profile from a different layer, we need to build it
    layer_profile = layer_profile or f"{project}-{account_name}-{sso_role.lower()}"

    return account_id, account_name, sso_role, layer_profile


def update_config_section(updater: ConfigUpdater, layer_profile: str, data: dict):
    """
    Update the <layer_profile> section with the values given on <data>.
    """
    section = get_or_create_section(updater, layer_profile)
    for key, value in data.items():
        section.set(key, value)

    updater.update_file()


def get_profiles(paths: PathsHandler):
    """
    Get the AWS profiles present on the layer by parsing some tf files.
    """
    raw_profiles = set()
    # these are files from the layer we are currently on
    for name in ("config.tf", "locals.tf", "runtime.tf"):
        try:
            tf_config = parse_tf_file(Path(paths.cwd / name))
        except FileNotFoundError:
            continue

        # get all the "profile" references from the file
        # but avoid lookup references (we will catch those profiles from locals.tf instead)
        raw_profiles.update(set(key_finder(tf_config, "profile", "lookup")))

    # the profile value from <layer>/config/backend.tfvars
    backend_config = parse_tf_file(paths.backend_tfvars)
    tf_profile = backend_config["profile"]

    return tf_profile, raw_profiles


def get_sso_access_token(sso_token_file: Path) -> str:
    """
    Get the SSO access token from the token file.
    """
    return json.loads(sso_token_file.read_text())["accessToken"]


def check_sso_token(paths: PathsHandler):
    """Check for the existence and validity of the SSO token to be used to get credentials."""

    # Adding `token` file name to this function in order to
    # meet the requirement regarding to have just one
    # token file in the sso/cache
    sso_role = paths.account_conf.get("sso_role")
    token_file = paths.sso_cache / sso_role

    token_files = list(paths.sso_cache.glob("*"))
    if not token_files:
        raise ExitError(1, "No AWS SSO token found. Please log in or configure SSO.")

    if token_file not in token_files and paths.sso_token_file not in token_files:
        raise ExitError(
            1,
            "No valid AWS SSO token found for current account.\n"
            "Please log out and reconfigure SSO before proceeding.",
        )

    token = json.loads(paths.sso_token_file.read_text())
    expiry = datetime.strptime(token.get("expiresAt"), "%Y-%m-%dT%H:%M:%SZ")
    renewal = datetime.now()

    if expiry < renewal:
        raise ExitError(
            1,
            "AWS SSO token has expired, please log back in by running [bold]leverage aws sso login[/bold]"
            " to refresh your credentials before re-running the last command.",
        )


def refresh_layer_credentials(paths: PathsHandler):
    tf_profile, raw_profiles = get_profiles(paths)
    config_updater = ConfigUpdater()
    config_updater.read(paths.aws_config_file)

    region = config_updater.get(f"profile {paths.project}-sso", "sso_region").value
    client = boto3.client("sso", region_name=region)
    for raw in raw_profiles:
        try:
            account_id, account_name, sso_role, layer_profile = get_layer_profile(
                raw,
                config_updater,
                tf_profile,
                paths.project,
            )
        except SkipProfile:
            continue

        # check if credentials need to be renewed
        try:
            expiration = int(config_updater.get(f"profile {layer_profile}", "expiration").value) / 1000
        except (NoSectionError, NoOptionError):
            # first time using this profile, skip into the credential's retrieval step
            logger.debug("No cached credentials found.")
        else:
            # we reduce the validity 30 minutes, to avoid expiration over long-standing tasks
            renewal = time.time() + (30 * 60)
            logger.debug(f"Token expiration time: {expiration}")
            logger.debug(f"Token renewal time: {renewal}")
            if renewal < expiration:
                # still valid, nothing to do with these profile!
                logger.info("Using already configured temporary credentials.")
                continue

        # retrieve credentials
        logger.debug(f"Retrieving role credentials for {sso_role}...")
        try:
            credentials = client.get_role_credentials(
                roleName=sso_role,
                accountId=account_id,
                accessToken=get_sso_access_token(paths.sso_token_file),
            )["roleCredentials"]
        except ClientError as error:
            if error.response["Error"]["Code"] in ("AccessDeniedException", "ForbiddenException"):
                raise ExitError(
                    40,
                    f"User does not have permission to assume role [bold]{sso_role}[/bold]"
                    " in this account.\nPlease check with your administrator or try"
                    " running [bold]leverage aws configure sso[/bold].",
                )

        # update expiration on aws/<project>/config
        logger.info(f"Writing {layer_profile} profile")
        update_config_section(
            config_updater,
            f"profile {layer_profile}",
            data={
                "expiration": credentials["expiration"],
            },
        )
        # write credentials on aws/<project>/credentials (create the file if it doesn't exist first)
        paths.aws_credentials_file.touch(exist_ok=True)
        credentials_updater = ConfigUpdater()
        credentials_updater.read(paths.aws_credentials_file)

        update_config_section(
            credentials_updater,
            layer_profile,
            data={
                "aws_access_key_id": credentials["accessKeyId"],
                "aws_secret_access_key": credentials["secretAccessKey"],
                "aws_session_token": credentials["sessionToken"],
            },
        )
        logger.info(f"Credentials for {account_name} account written successfully.")
