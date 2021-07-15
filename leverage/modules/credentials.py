"""
    Credentials managing module.
"""
import re
import json
from pathlib import Path

import click
from click.exceptions import Exit
import questionary
from questionary import Choice
from ruamel.yaml import YAML

from leverage import logger
from leverage.path import get_home_path
from leverage.modules.terraform import awscli
from leverage.modules.terraform import run as tfrun
from leverage.modules.project import PROJECT_CONFIG
from leverage.modules.project import render_file
from leverage._internals import MutuallyExclusiveOption


# Regexes for general validation
PROJECT_SHORT = r"[a-z]{2}"
USERNAME = r"[a-zA-Z0-9\.\-_]+" # NOTE: Is this thorough enough?
KEY_ID = r"[A-Z0-9]{20}"
SECRET_KEY = r"[a-zA-Z0-9]{40}"
REGION = (r"[a-z]{2}-[gov-]?"
          r"(?:central|north|south|east|west|northeast|northwest|southeast|southwest|secret|topsecret)-[1-3]")
ACCOUNT_ID = r"[0-9]{12}"
CREDENTIALS_FILE = fr"Access key ID,Secret access key\s+(?P<key_id>{KEY_ID}),(?P<secret_key>{SECRET_KEY})"

AWSCLI_CONFIG_DIR = Path(get_home_path()) / ".aws"

PROFILES = {
    "bootstrap": {
        "choice_title": "Bootstrap credentials (temporary)",
        "profile_role": "oaar",
        "role": "OrganizationAccountAccessRole",
        "mfa": False
    },
    "management": {
        "choice_title": "Management credentials",
        "profile_role": "oaar",
        "role": "OrganizationAccountAccessRole",
        "mfa": True
    },
    "security": {
        "choice_title": "DevOps credentials",
        "profile_role": "devops",
        "role": "DevOps",
        "mfa": True
    }
}


def _ask_for_short_name():
    """ Prompt for project short name or quit application if user cancels mid input process.

    Raises:
        Exit: When the user cancels input.

    Returns:
        str: Project short name.
    """
    short_name = questionary.text(
        message="Short name:",
        qmark=">",
        validate=lambda value: bool(re.fullmatch(PROJECT_SHORT, value)) or "The project short name should be a two letter lowercase word"
    ).ask()

    if not short_name:
        raise Exit(1)
    return short_name


def _ask_for_region():
    """ Prompt for region or quit application if user cancels mid input process.

    Raises:
        Exit: When the user cancels input.

    Returns:
        str: Region.
    """
    region = questionary.text(
        message="Region:",
        qmark=">",
        validate=lambda value: bool(re.fullmatch(REGION, value)) or "Invalid region."
    )

    if not region:
        raise Exit(1)
    return region


def _ask_for_profile():
    """ Prompt for profile selection or quit application if user cancels mid input process.

    Raises:
        Exit: When the user cancels input.

    Returns:
        str : Profile to configure.
    """
    profile = questionary.select(
        message="Select the credentials to set:",
        qmark=">",
        choices=[Choice(profile["choice_title"], value=name) for name, profile in PROFILES.items()]
    ).ask()

    if not profile:
        raise Exit(1)
    return profile


def _ask_for_credentials_location():
    """ Prompt for credential input method and location if path is selected.
    Quit application if user cancels mid input process.

    Raises:
        Exit: When the user cancels input.

    Returns:
        Path | None: Path to location or none if `Manual` is selected.
    """
    location = questionary.prompt([
        {
            "type": "select",
            "name": "input_type",
            "message": "Select the means by which you'll provide the programatic keys:",
            "qmark": ">",
            "choices": [
                {"name": "Path to an access keys file obtained from AWS", "value": "path"},
                {"name": "Manually", "value": "manual"}
            ]
        },
        {
            "type": "path",
            "name": "path",
            "message": "Path to access keys file:",
            "qmark": ">",
            "when": lambda qs: qs["input_type"] == "path",
            "validate": lambda value: (Path(value).is_file() and Path(value).exists()) or "Path must be an existing file"
        }
    ])

    if not location:
        raise Exit(1)
    location = location.get("path")
    return Path(location) if location else location


def _ask_for_credentials():
    """ Prompt for key id and secret keys or quit application if user cancels mid input process.

    Raises:
        Exit: When the user cancels input.

    Returns:
        str, str: Kei ID, Secret Key
    """
    credentials = questionary.prompt([
        {
            "type": "text",
            "name": "key_id",
            "message": "Key:",
            "qmark": ">",
            "validate": lambda value: bool(re.fullmatch(KEY_ID, value)) or "Invalid Key"
        },
        {
            "type": "password",
            "name": "secret_key",
            "message": "Secret:",
            "qmark": ">",
            "validate": lambda value: bool(re.fullmatch(SECRET_KEY, value)) or "Invalid Secret",
        }
    ])

    if not credentials:
        raise Exit(1)
    return list(credentials.values())


def _ask_for_username():
    """ Prompt for username or quit application if user cancels mid input process.

    Raises:
        Exit: When the user cancels input.

    Returns:
        str: User name.
    """
    username = questionary.text(
        message="User associated to credentials:",
        qmark=">",
        validate=lambda value: bool(re.fullmatch(USERNAME, value)) or "Invalid username."
    ).ask()

    if not username:
        raise Exit(1)
    return username


@click.group()
def credentials():
    """ Manage AWS cli credentials. """
    # NOTE: Workaround until we remove root build.env
    if not render_file("build.env"):
        raise Exit(1)


def _profile_is_configured(profile):
    """ Check if given profile is already configured.

    Args:
        profile (str): Profile to check.

    Returns:
        bool: Whether the profile was already configured or not.
    """
    exit_code, _ = awscli(f"configure list --profile {profile}")

    return not exit_code


def _extract_credentials(file):
    """ Extract AWS credentials from given file. Print message and quit application if file is malformed.
    Access Keys files have the form:
       Access key ID,Secret access key
       AKUDKXXXXXXXXXXXXXXX,examplesecreteLkyvWWjxi29dJ63Geo1Ggl956b

    Args:
        file (Path): Credentials file as obtained from AWS Console.

    Raises:
        Exit: When file content does not conform to expected form.

    Returns:
        str, str: Key ID, Secret Key
    """
    match = re.match(pattern=fr"Access key ID,Secret access key\s+(?P<key_id>{KEY_ID}),(?P<secret_key>{SECRET_KEY})",
                     string=file.read_text())

    if not match:
        click.echo("\nMalformed access keys file\n")
        raise Exit(1)

    return match.groups()


def configure_default_profile(region):
    """ Set default profile values.

    Args:
        region (str): Region.
    """
    default = {
        "output": "json",
        "region": region
    }

    for key, value in default.items():
        awscli(f"configure set {key} {value}")


def _backup_file(filename):
    """ Create backup of a credential file using docker image.

    Args:
        filename (str): File to backup, either `config` or `credentials`
    """
    credential_files_env_vars = {
        "config": "AWS_CONFIG_FILE",
        "credentials": "AWS_SHARED_CREDENTIALS_FILE"
    }
    env_var = credential_files_env_vars.get(filename)

    tfrun(entrypoint="/bin/sh -c",
          command=f"'cp ${env_var} \"${{{env_var}}}_bkp\"'",
          enable_mfa=False,
          interactive=False)


def configure_credentials(profile, file=None, key_id=None, secret_key=None, make_backup=False):
    """ Set credentials in `credentials` file for AWS cli. Make backup if required.

    Args:
        profile (str): Name of the profile to configure.
        file (Path, optional): Credentials file. Defaults to None.
        key_id (str, optional): AWS access key ID. Defaults to None.
        secret_key (str, optional): AWS secret access key. Defaults to None.
        make_backup (bool, optional): Whether to make a backup of the credentials file. Defaults to False.
    """
    if not any([file, key_id, secret_key]):
        file = _ask_for_credentials_location()

    if file:
        key_id, secret_key = _extract_credentials(file)

    if not key_id and not secret_key:
        key_id, secret_key = _ask_for_credentials()

    if make_backup:
        logger.info("Backing up credentials file.")
        _backup_file("credentials")

    values = {
        "aws_access_key_id": key_id,
        "aws_secret_access_key": secret_key
    }

    for key, value in values.items():
        awscli(f"configure set {key} {value} --profile {profile}")


def _get_management_account_id(profile):
    """ Get management account id through AWS cli.

    Args:
        profile (str): Name of profile to configure.

    Returns:
        str: Management account id.
    """
    _, caller_identity = awscli(f"--output json sts get-caller-identity --profile {profile}")

    caller_identity = json.loads(caller_identity)
    return caller_identity["Account"]


@credentials.command()
@click.option("--file",
              cls=MutuallyExclusiveOption,
              conflicting_options=["key_id", "secret_key"],
              type=click.Path(exists=True, path_type=Path),
              help="Path to AWS cli credentials file.")
@click.option("--key-id",
              cls=MutuallyExclusiveOption,
              conflicting_options=["file"],
              help="AWS cli access key ID.")
@click.option("--secret-key",
              cls=MutuallyExclusiveOption,
              conflicting_options=["file"],
              help="AWS cli access secret key.")
def create(file, key_id, secret_key):
    """ Initialize credentials for the project.

    Configure the required credentials for the bootstrap process and a default profile.
    Fetch management account id and update project configuration file.
    """
    project_config = {}
    if PROJECT_CONFIG.exists():
        logger.info("Loading project config file.")
        project_config = YAML().load(PROJECT_CONFIG)

    short_name = project_config.get("short_name") or _ask_for_short_name()
    region = project_config.get("primary_region") or _ask_for_region()
    profile_name = f"{short_name}-bootstrap"

    if _profile_is_configured(profile=profile_name):
        logger.error("Bootstrap credentials already set.")
        return

    credentials_dir = AWSCLI_CONFIG_DIR / short_name

    logger.info("Configuring default profile information.")
    configure_default_profile(region)
    profiles_config = credentials_dir / "config"
    logger.info(f"[bold]Default profile configured in:[/bold] {profiles_config.as_posix()}")

    logger.info("Configuring [bold]bootstrap[/bold] credentials.")
    configure_credentials(profile=profile_name,
                          file=file,
                          key_id=key_id,
                          secret_key=secret_key)
    credentials_config = credentials_dir / "credentials"
    logger.info(f"[bold]Bootstrap credentials configured in:[/bold] {credentials_config.as_posix()}")

    accounts = project_config.get("organization").get("accounts")
    management_account = next((account for account in accounts if account["name"] == "management"), None)
    if management_account:
        logger.info("Fetching management account id.")
        management_account["id"] = int(_get_management_account_id(profile=profile_name))

        logger.info("Updating project configuration file.")
        YAML().dump(data=project_config, stream=PROJECT_CONFIG)

    logger.info("Finished setting up [bold]bootstrap[/bold] credentials.")


def _organization_is_created(profile):
    """ Check if account is part of an organization.
    Output when negative:
        An error occurred (AWSOrganizationsNotInUseException) when calling the DescribeOrganization
        operation: Your account is not a member of an organization.
    Exit code when negative:
        255

    Args:
        profile (str): Name of profile to configure.
        management_id (str | int): Management account id.

    Returns:
        bool: Whether the organization exists or not.
    """
    exit_code, _ = awscli(f"--output json organizations describe-organization --profile {profile}")

    return not exit_code


def _get_organization_accounts(profile, project_name):
    """ Get organization accounts names and ids. Removing the prefixed project name from the account names.

    Args:
        profile (str): Name of profile to configure.
        project_name (str): Name of the project.

    Returns:
        dict: Mapping of organization accounts names to ids.
    """
    _, organization_accounts = awscli(f"--output json organizations list-accounts --profile {profile}")
    organization_accounts = json.loads(organization_accounts)["Accounts"]

    prefix = f"{project_name}-"
    accounts = {}
    for account in organization_accounts:
        name = account["Name"]
        name = name[len(prefix):] if name.startswith(prefix) else name
        accounts[name] = account["Id"]

    return accounts


def _get_mfa_serial(profile, username):
    """ Get MFA serial for the profile and user given.

    Args:
        profile (str): Name of profile.
        username (str): User name.

    Returns:
        str: MFA device serial.
    """
    _, mfa_devices = awscli(f"--output json iam list-mfa-devices --profile {profile}")

    mfa_devices = json.loads(mfa_devices)
    return next((device["SerialNumber"] for device in mfa_devices["MFADevices"] if device["UserName"] == username), "")


def configure_profile(profile, values):
    """ Set profile in `config` file for AWS cli.

    Args:
        profile (str): Profile name.
        values (dict): Mapping of values to be set in the profile.
    """
    for key, value in values.items():
        awscli(f"configure set {key} {value} --profile {profile}")


def configure_accounts_profiles(profile_name, region, username, organization_accounts, project_accounts):
    """ Set up the required profiles for all accounts to be used with AWS cli. Backup previous profiles.

    Args:
        profile_name (str): Name of the profile to configure.
        region (str): Region.
        username (str): Name of user associated with the credentials.
        organization_accounts (dict): Name and id of all accounts in the organization.
        project_accounts (dict): Name and email of all accounts in project configuration file.
    """
    short_name, profile = profile_name.split("-")

    mfa_serial = None
    if PROFILES[profile]["mfa"]:
        logger.info("Fetching MFA device serial.")
        mfa_serial = _get_mfa_serial(profile_name, username)
        if not mfa_serial:
            logger.error("No MFA device found for user. Please set up a device before configuring the accounts profiles.")
            raise Exit(1)

    account_profiles = {}
    for account in project_accounts:
        account_name = account["name"]
        try: # Account in config file may not be already created
            account_id = organization_accounts[account_name]
        except KeyError:
            continue

        account_profile = {
            "output": "json",
            "region": region,
            "role_arn": f"arn:aws:iam::{account_id}:role/{PROFILES[profile]['role']}",
            "source_profile": profile_name
        }
        if mfa_serial:
            account_profile["mfa_serial"] = mfa_serial

        # A profile identifier looks like `le-security-oaar`
        account_profiles[f"{short_name}-{account_name}-{PROFILES[profile]['profile_role']}"] = account_profile

    logger.info("Backing up account profiles file.")
    _backup_file("config")

    for profile_identifier, profile_values in account_profiles.items():
        configure_profile(profile_identifier, profile_values)


@credentials.command()
@click.option("--profile",
              type=click.Choice(["bootstrap",
                                 "management",
                                 "security"],
                                case_sensitive=False),
              help="Profile credentials to set.")
@click.option("--file",
              cls=MutuallyExclusiveOption,
              conflicting_options=["key_id", "secret_key"],
              type=click.Path(exists=True, path_type=Path),
              help="Path to AWS cli credentials file.")
@click.option("--key-id",
              cls=MutuallyExclusiveOption,
              conflicting_options=["file"],
              help="AWS cli access key ID.")
@click.option("--secret-key",
              cls=MutuallyExclusiveOption,
              conflicting_options=["file"],
              help="AWS cli access secret key.")
@click.option("--username",
              help="Name of the user associated with the given credentials. "
                   "Used when setting a profile with MFA enabled, ignored otherwise.")
@click.option("--only-account-profiles",
              is_flag=True,
              help="Only update accounts' profiles, don't change key/secret.")
def update(profile, file, key_id, secret_key, username, only_account_profiles):
    """ Update credentials for the given profile.

    Only to be run after having initialized the project credentials. Generate the profiles for all
    accounts in the project attaching MFA serial if the credentials require so.

    Backup previously existent credentials if necessary and update the project configuration file with
    the ids for all accounts.
    """
    project_config = {}
    if PROJECT_CONFIG.exists():
        logger.info("Loading config file.")
        project_config = YAML().load(PROJECT_CONFIG)

    short_name = project_config.get("short_name") or _ask_for_short_name()
    region = project_config.get("primary_region") or _ask_for_region()

    if not _profile_is_configured(profile=f"{short_name}-bootstrap"):
        logger.error("Credentials haven't been created, please run the credentials creation command first.")
        return

    profile = profile or _ask_for_profile()
    profile_name = f"{short_name}-{profile}"

    credentials_dir = AWSCLI_CONFIG_DIR / short_name
    credentials_config = credentials_dir / "credentials"
    profiles_config = credentials_dir / "config"

    if PROFILES[profile]["mfa"]:
        username = username or _ask_for_username()

    already_configured = _profile_is_configured(profile=profile_name)
    if not only_account_profiles:
        logger.info(f"Configuring [bold]{profile}[/bold] credentials.")
        configure_credentials(profile_name, file, key_id, secret_key, make_backup=already_configured)
        logger.info(f"[bold]{profile.capitalize()} credentials configured in:[/bold] {credentials_config.as_posix()}")

    elif not already_configured:
        logger.error("Credentials for this profile haven't been configured yet.\n"
                     "Please re-run the command without the [bold]--only-account-profiles[/bold] flag.")

    project_accounts = project_config.get("organization").get("accounts")
    if _organization_is_created(profile=profile_name) and project_accounts:
        logger.info("Configuring accounts' profiles.")
        project_name = project_config.get("project_name")

        logger.info("Fetching organization accounts.")
        organization_accounts = _get_organization_accounts(profile=profile_name, project_name=project_name)

        configure_accounts_profiles(profile_name, region, username, organization_accounts, project_accounts)
        logger.info(f"[bold]Account profiles configured in:[/bold] {profiles_config.as_posix()}")

        for account in project_accounts:
            try: # Account in config file may not be already created
                account["id"] = int(organization_accounts[account["name"]])
            except KeyError:
                continue

        logger.info("Updating project configuration file.")
        YAML().dump(data=project_config, stream=PROJECT_CONFIG)

        # Update common.tfvars if it exists
        try:
            render_file("config/common.tfvars")
        except FileNotFoundError:
            pass

    logger.info(f"Finished updating [bold]{profile}[/bold] credentials.")
