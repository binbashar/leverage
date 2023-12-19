# TODO: this is not a container, move this whole file elsewhere
import boto3

from configupdater import ConfigUpdater

from leverage import logger
from leverage.container import AWSCLIContainer


def get_account_roles(sso_region: str, access_token: str) -> dict:
    """
    Fetch the accounts and roles from the user.
    """
    client = boto3.client("sso", region_name=sso_region)
    account_roles = {}

    accounts = client.list_accounts(accessToken=access_token)
    for account in accounts["accountList"]:
        acc_role = client.list_account_roles(
            accessToken=access_token,
            accountId=account["accountId"],
            maxResults=1,  # assume the first role is always the correct one
        )["roleList"][0]

        account_roles[account["accountName"]] = {
            "account_id": acc_role["accountId"],
            "role_name": acc_role["roleName"],
        }

    return account_roles


def add_sso_profile(
    config_updater: ConfigUpdater, section_name: str, role_name: str, account_id: str, region: str, start_url: str
):
    """
    Add a profile to the config file.
    """
    if not config_updater.has_section(section_name):
        config_updater.add_section(section_name)
    # add_section doesn't return the section object, so we need to retrieve it either case
    section = config_updater.get_section(section_name)

    data = {
        "role_name": role_name,
        "account_id": account_id,
        "sso_region": region,
        "sso_start_url": start_url,
    }
    for k, v in data.items():
        # can't set a dict directly, so we need to go field by field
        section[k] = v


def configure_sso_profiles(cli: AWSCLIContainer):
    """
    Populate the ~./aws/<project>/config file with the sso profiles from the accounts.
    """
    updater = ConfigUpdater()
    updater.read(cli.paths.host_aws_profiles_file)

    # set the default profile first
    default_sso_profile_name = f"profile {cli.project}-sso"
    default_profile = updater[default_sso_profile_name]
    region = default_profile["sso_region"].value
    start_url = default_profile["sso_start_url"].value

    # then a profile for each account
    access_token = cli.get_sso_access_token()
    logger.info(f"Fetching accounts and roles...")
    account_roles = get_account_roles(region, access_token)
    for acc_name, values in account_roles.items():
        # account names comes in the form of: {long project name}-{account name}
        short_acc_name = acc_name.replace(cli.paths.project_long + "-", "")
        section_name = f"profile {cli.project}-sso-{short_acc_name}"
        logger.info(f"Adding {section_name}")
        add_sso_profile(updater, section_name, values["role_name"], values["account_id"], region, start_url)

    # save/update the profile file
    updater.update_file()
