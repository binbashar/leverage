import time
from configparser import NoSectionError, NoOptionError

import boto3
import hcl2
from configupdater import ConfigUpdater

from leverage import logger
from leverage._utils import key_finder, ExitError, get_or_create_section


class SkipProfile(Exception):
    pass


def get_layer_profile(raw_profile: str, config_updater: ConfigUpdater, tf_profile: str, project: str):
    if "local." in raw_profile:
        # ignore values referencing to local variables
        # we will search for profiles directly in locals.tf instead
        raise SkipProfile

    # if it is exactly that variable, we already know the layer profile is tf_profile
    layer_profile = tf_profile if raw_profile == "${var.profile}" else None

    # replace variables with their corresponding values
    raw = raw_profile.replace("${var.profile}", tf_profile).replace("${var.project}", project)

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

    # if we are processing a profile from a different layer, we need to built it
    layer_profile = layer_profile or f"{project}-{account_name}-{sso_role.lower()}"

    return account_id, account_name, sso_role, layer_profile


def refresh_layer_credentials(cli):
    raw_profiles = set()
    # these are files from the layer we are currently on
    for name in ("config.tf", "locals.tf"):
        with open(name) as tf_file:
            tf_config = hcl2.load(tf_file)
        # get all the "profile" references from the file
        raw_profiles.update(set(key_finder(tf_config, "profile")))

    # the profile value from <layer>/config/backend.tfvars
    with open(cli.paths.local_backend_tfvars) as backend_config_file:
        backend_config = hcl2.load(backend_config_file)
    tf_profile = backend_config["profile"]

    config_updater = ConfigUpdater()
    config_updater.read(cli.paths.host_aws_profiles_file)

    credentials_updater = ConfigUpdater()
    with open(cli.paths.host_aws_credentials_file, "a+") as credentials_file:
        credentials_updater.read_file(credentials_file)

    client = boto3.client("sso", region_name=cli.sso_region_from_main_profile)
    for raw in raw_profiles:
        try:
            account_id, account_name, sso_role, layer_profile = get_layer_profile(
                raw,
                config_updater,
                tf_profile,
                cli.project,
            )
        except SkipProfile:
            continue

        # check if credentials need to be renewed
        try:
            expiration = int(config_updater.get(f"profile {layer_profile}", "expiration").value) / 1000
        except (NoSectionError, NoOptionError):
            # first time using this profile, skip into the credential's retrieval step
            logger.debug(f"No cached credentials found.")
        else:
            # we reduce the validity 30 minutes, to avoid expiration over long-standing tasks
            now = time.time() + (30 * 60)
            if now < expiration:
                # still valid, nothing to do with these profile!
                logger.info("Using already configured temporary credentials.")
                continue

        # retrieve credentials
        logger.debug(f"Retrieving role credentials for {sso_role}...")
        credentials = client.get_role_credentials(
            roleName=sso_role,
            accountId=account_id,
            accessToken=cli.get_sso_access_token(),
        )["roleCredentials"]

        # update expiration on aws/<project>/config
        logger.info(f"Writing {layer_profile} profile")
        config_section = get_or_create_section(config_updater, f"profile {layer_profile}")
        config_section.set("expiration", credentials["expiration"])
        config_updater.update_file()

        # write credentials on aws/<project>/credentials
        credentials_section = get_or_create_section(credentials_updater, layer_profile)
        credentials_section.set("aws_access_key_id", credentials["accessKeyId"])
        credentials_section.set("aws_secret_access_key", credentials["secretAccessKey"])
        credentials_section.set("aws_session_token", credentials["sessionToken"])
        credentials_updater.update_file()

        logger.info(f"Credentials for {account_name} account written successfully.")
