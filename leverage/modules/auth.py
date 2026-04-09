import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps
from configparser import NoSectionError, NoOptionError

import boto3
import click
from dateutil.tz import tzutc
from configupdater import ConfigUpdater
from botocore.session import get_session
from botocore.exceptions import ClientError

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
    layer_profile = tf_profile if raw_profile in ("var.profile", "each.value.profile") else None

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


def _perform_authentication(paths: PathsHandler):
    """Perform authentication checks and credential refresh.

    This function contains the core authentication logic that checks for SSO or MFA
    configuration and refreshes credentials accordingly. Only authenticates when
    in a layer location.

    Args:
        paths: PathsHandler instance containing project paths and configuration
    """
    if paths.get_location_type() == "layer":
        if paths.common_conf.get("sso_enabled", False):
            check_sso_token(paths)
            refresh_layer_credentials(paths)
        elif paths.mfa_enabled:
            refresh_layer_credentials_mfa(paths)


def authenticate(command):
    """Decorator to require authentication before running a command.

    This decorator extracts the PathsHandler from the Click context and performs
    authentication checks before executing the wrapped command. It handles both SSO
    and MFA authentication based on the project configuration.

    Usage:
        @click.command()
        @authenticate
        @pass_paths
        @pass_runner
        def some_command(tf: TFRunner, paths: PathsHandler, args):
            # command logic
    """

    @wraps(command)
    def new_command(*args, **kwargs):
        ctx = click.get_current_context()
        paths = ctx.obj.paths
        _perform_authentication(paths)
        return command(*args, **kwargs)

    return new_command


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
            else:
                raise ExitError(50, f"Error retrieving role credentials: {error}")

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


def refresh_layer_credentials_mfa(paths: PathsHandler):
    tf_profile, raw_profiles = get_profiles(paths)
    config_updater = ConfigUpdater()
    config_updater.read(paths.aws_config_file)

    # Create STS client with source profile credentials
    session = get_session()
    session.set_config_variable("credentials_file", paths.aws_credentials_file.as_posix())
    session.set_config_variable("config_file", paths.aws_config_file.as_posix())

    for raw_profile in raw_profiles:
        if "local." in raw_profile:
            # ignore values referencing to local variables
            # we will search for profiles directly in locals.tf instead
            continue

        # if it is exactly that variable, we already know the layer profile is tf_profile
        layer_profile = tf_profile if raw_profile in ("var.profile", "each.value.profile") else None

        # replace variables with their corresponding values
        profile_name = (
            raw_profile.replace("${var.profile}", tf_profile)
            .replace("${var.project}", paths.project)
            .replace("each.value.profile", tf_profile)
        )

        # if layer_profile wasn't set, use profile_name
        if layer_profile is None:
            layer_profile = profile_name

        logger.info(f"Attempting to get temporary credentials for {profile_name} profile.")
        if profile := config_updater.get_section(f"profile {profile_name}-mfa"):
            role_arn = profile.get("role_arn").value
            mfa_serial = profile.get("mfa_serial").value
            source_profile = profile.get("source_profile").value
        else:
            raise ExitError(
                40,
                f"Credentials for profile {profile_name} have not been properly configured. Please check your configuration.\n"
                f"Check the following link for possible solutions: https://leverage.binbash.co/user-guide/troubleshooting/credentials/",
            )

        if not paths.aws_cache_dir.exists():
            paths.aws_cache_dir.mkdir(parents=True)

        cache_file = paths.aws_cache_dir / profile_name
        if cache_file.exists():
            logger.debug(f"Found cached credentials in {cache_file}.")
            cached_credentials = json.loads(cache_file.read_text())

            expiration = datetime.strptime(cached_credentials.get("Expiration"), "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=tzutc()
            )
            renewal = datetime.now(tzutc()) + timedelta(seconds=(30 * 60))
            if renewal < expiration:
                logger.info("Using cached credentials.")
                continue

        else:
            logger.debug("No cached credentials found.")

        client_session = boto3.Session(botocore_session=session, profile_name=source_profile)
        client = client_session.client("sts")
        credentials = None
        for _ in range(3):
            try:
                mfa_token_code = click.prompt("Enter MFA token code", type=str)
            except click.exceptions.Abort:
                raise ExitError(1, "Aborted by user.")

            try:
                credentials = client.assume_role(
                    RoleArn=role_arn,
                    RoleSessionName=f"leverage-{profile_name}",
                    SerialNumber=mfa_serial,
                    TokenCode=mfa_token_code,
                )
                credentials = credentials["Credentials"]
                credentials["Expiration"] = credentials["Expiration"].strftime("%Y-%m-%dT%H:%M:%SZ")
                cache_file.write_text(json.dumps(credentials))
                break

            except ClientError as error:
                if "invalid MFA" in error.response["Error"]["Message"]:
                    logger.error("Unable to get valid credentials. Please try again.")
                    continue
                elif error.response["Error"]["Code"] == "AccessDeniedException":
                    raise ExitError(
                        40,
                        f"User does not have permission to assume role [bold]{role_arn}[/bold]"
                        " in this account.\nPlease check with your administrator or try"
                        " checking your credentials configuration.",
                    )
                elif error.response["Error"]["Code"] == "ExpiredToken":
                    logger.error("Token has expired. Please try again.")
                    continue
                elif (
                    error.response["Error"]["Code"] == "ValidationError"
                    and "Invalid length for parameter TokenCode" in error.response["Error"]["Message"]
                ):
                    logger.error("Invalid token length, it must be 6 digits long. Please try again.")
                    continue
                elif "An error occurred" in error.response["Error"]["Message"]:
                    raise ExitError(50, f"Error assuming role: {error}")

        if credentials is None:
            raise ExitError(60, "Failed to get credentials after 3 attempts. Please try again later.")

        # write credentials on aws/<project>/credentials (create the file if it doesn't exist first)
        paths.aws_credentials_file.touch(exist_ok=True)
        credentials_updater = ConfigUpdater()
        credentials_updater.read(paths.aws_credentials_file)

        update_config_section(
            credentials_updater,
            layer_profile,
            data={
                "aws_access_key_id": credentials["AccessKeyId"],
                "aws_secret_access_key": credentials["SecretAccessKey"],
                "aws_session_token": credentials["SessionToken"],
            },
        )
        logger.info(f"Credentials written successfully.")
