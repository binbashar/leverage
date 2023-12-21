import time
from configparser import NoSectionError, NoOptionError

import boto3
import hcl2
from configupdater import ConfigUpdater

from leverage import logger
from leverage._utils import key_finder, ExitError, get_or_create_section


def get_layer_profile():
    pass


def refresh_layer_credentials(cli):
    # this is the config.tf file from the layer we are currently on
    with open("config.tf") as tf_config_file:
        tf_config = hcl2.load(tf_config_file)

    # get all the "profile" references from the config file
    raw_profiles = set(key_finder(tf_config, "profile"))

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
        # if it is exactly that variable, we already know the layer profile is tf_profile
        layer_profile = tf_profile if raw == "${var.profile}" else None

        # replace variables with their corresponding values
        raw = raw.replace("${var.profile}", tf_profile).replace("${var.project}", cli.project)

        # the project and the role are at the beginning and end of the string
        project, *account_name, role = raw.split("-")
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

        # check if credentials need to be renewed
        try:
            expiration = int(config_updater.get(tf_profile, "expiration").value) / 1000
        except (NoSectionError, NoOptionError):
            # first time using this profile, skip into the credential's retrieval step
            pass
        else:
            # we got temporal credentials with an expiration, let's check if they are still valids
            renewal_time = time.time() + (30 * 60)  # at least 30 minutes of validity, otherwise consider it expired
            if renewal_time > expiration:
                # still valid, nothing to do with these profile!
                logger.info("Using already configured temporary credentials.")
                continue

        # retrieve credentials
        logger.info(f"Retrieving role credentials for {sso_role} in account {account_name}...")
        credentials = client.get_role_credentials(
            roleName=sso_role,
            accountId=account_id,
            accessToken=cli.get_sso_access_token(),
        )["roleCredentials"]

        # if we are on the same layer than the account (check we did at the , use the profile from backend.tfvars
        layer_profile = layer_profile or f"{project}-{account_name}-{sso_role.lower()}"

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
