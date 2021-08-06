"""
    Credentials managing module.
"""
import re
import json
from pathlib import Path
from functools import wraps

import click
from click.exceptions import Exit
import questionary
from questionary import Choice
from ruamel.yaml import YAML

from leverage import logger
from leverage.path import get_home_path
from leverage._internals import pass_state
from leverage.modules.terraform import awscli
from leverage.modules.terraform import run as tfrun
from leverage.modules.project import render_file
from leverage.modules.project import PROJECT_CONFIG
from leverage.modules.project import load_project_config


# Regexes for general validation
PROJECT_SHORT = r"[a-z]{2}"
USERNAME = r"[a-zA-Z0-9\+,=\.@\-_]{1,64}" # https://docs.aws.amazon.com/IAM/latest/UserGuide/id_users_create.html#id_users_create_console
                                          # https://docs.aws.amazon.com/IAM/latest/APIReference/API_CreateUser.html#API_CreateUser_RequestParameters
KEY_ID = r"[A-Z0-9]{20}"
SECRET_KEY = r"[a-zA-Z0-9/\+]{40}"
REGION = (r"[a-z]{2}-[gov-]?"
          r"(?:central|north|south|east|west|northeast|northwest|southeast|southwest|secret|topsecret)-[1-3]")
ACCOUNT_ID = r"[0-9]{12}"
MFA_SERIAL = fr"arn:aws:iam::{ACCOUNT_ID}:mfa/{USERNAME}"
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


def _exit_if_user_cancels_input(question):
    """ Prompt user for input, exit application if user cancels it.

    Args:
        question (callable): Question to be asked to user.

    Raises:
        Exit: When user cancels input.

    Returns:
        any: Question return value
    """

    @wraps(question)
    def handle_keyboard_interrupt(*args, **kwargs):
        answer = question(*args, **kwargs)
        if answer is None:
            raise Exit(1)
        return answer

    return handle_keyboard_interrupt


@_exit_if_user_cancels_input
def _ask_for_short_name():
    """ Prompt for project short name.

    Returns:
        str: Project short name.
    """
    return questionary.text(
        message="Short name:",
        qmark=">",
        validate=lambda value: bool(re.fullmatch(PROJECT_SHORT, value)) or "The project short name should be a two letter lowercase word"
    ).ask()


@_exit_if_user_cancels_input
def _ask_for_region():
    """ Prompt for region.

    Returns:
        str: Region.
    """
    return questionary.text(
        message="Region:",
        qmark=">",
        validate=lambda value: bool(re.fullmatch(REGION, value)) or "Invalid region."
    ).ask()


@_exit_if_user_cancels_input
def _ask_for_profile():
    """ Prompt for profile selection.

    Returns:
        str : Profile to configure.
    """
    return questionary.select(
        message="Select the credentials to set:",
        qmark=">",
        choices=[Choice(profile["choice_title"], value=name) for name, profile in PROFILES.items()]
    ).ask()


@_exit_if_user_cancels_input
def _ask_for_credentials_overwrite(profile, skip_option_title, overwrite_option_title):
    """ Prompt user with options regarding already existing credentials, whether to 
    skip their configuration or overwrite them.

    Args:
        profile (str): Name of the profile being configured.
        skip_option_title (str): Message to display in the `skip` option.
        overwrite_option_title (str): Message to display in the `overwrite` option.

    Returns:
        bool: Whether to overwrite the current credentials or not.
    """
    return questionary.select(
        message=f"Credentials already configured for {profile}:",
        qmark=">",
        choices=[
            Choice(skip_option_title,
                   value=False,
                   shortcut_key="s",
                   checked=True),
            Choice(overwrite_option_title,
                   value=True,
                   shortcut_key="o")
        ],
        use_shortcuts=True
    ).ask()


@_exit_if_user_cancels_input
def _ask_for_credentials_location():
    """ Prompt for credential input method and location if path is selected.

    Returns:
        Path | str: Path to location or `manual` if `Manual` is selected.
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
        return

    input_type = location.get("input_type")
    return Path(location.get("path")) if input_type == "path" else input_type


@_exit_if_user_cancels_input
def _ask_for_credentials():
    """ Prompt for key id and secret keys.

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
        return

    return list(credentials.values())


@click.group()
@pass_state
def credentials(state):
    """ Manage AWS cli credentials. """
    state.project_config = load_project_config()

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
          command=f"'cp ${env_var} \"${{{env_var}}}.bkp\"'",
          enable_mfa=False,
          interactive=False)


def configure_credentials(profile, file=None, make_backup=False):
    """ Set credentials in `credentials` file for AWS cli. Make backup if required.

    Args:
        profile (str): Name of the profile to configure.
        file (Path, optional): Credentials file. Defaults to None.
        make_backup (bool, optional): Whether to make a backup of the credentials file. Defaults to False.
    """
    file = file or _ask_for_credentials_location()

    if file is not None and file != "manual":
        key_id, secret_key = _extract_credentials(file)

    else:
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


def _credentials_are_valid(profile):
    """ Check if credentials for given profile are valid.
    If credentials are invalid, the command output will be as follows:
    Exit code:
        255
    Error message:
        An error occurred (InvalidClientTokenId) when calling the GetCallerIdentity operation:
        The security token included in the request is invalid.

    Args:
        profile (str): Name of profile for which credentials must be checked.

    Returns:
        bool: Whether the credentials are valid.
    """
    error_code, output = awscli(f"sts get-caller-identity --profile {profile}")

    return error_code != 255 and "InvalidClientTokenId" not in output


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
              type=click.Path(exists=True, path_type=Path),
              help="Path to AWS cli credentials file.")
@click.option("--force",
              is_flag=True,
              help="Force credentials creation, even if they are already configured.")
@pass_state
def create(state, file, force):
    """ Initialize credentials for the project.

    Configure the required credentials for the bootstrap process and a default profile.
    Fetch management account id and update project configuration file.
    """
    project_config = state.project_config

    short_name = project_config.get("short_name") or _ask_for_short_name()
    region = project_config.get("primary_region") or _ask_for_region()
    profile_name = f"{short_name}-bootstrap"

    credentials_dir = AWSCLI_CONFIG_DIR / short_name

    if _profile_is_configured(profile=profile_name):
        if not (force
                    or _ask_for_credentials_overwrite(
                        profile="bootstrap",
                        skip_option_title="Skip credentials configuration.",
                        overwrite_option_title="Overwrite current credentials."
                    )
                ):
            logger.info("Exiting credentials configuration.")
            return

    logger.info("Configuring default profile information.")
    configure_default_profile(region)
    profiles_config = credentials_dir / "config"
    logger.info(f"[bold]Default profile configured in:[/bold] {profiles_config.as_posix()}")

    logger.info("Configuring [bold]bootstrap[/bold] credentials.")
    configure_credentials(profile=profile_name, file=file)
    credentials_config = credentials_dir / "credentials"
    logger.info(f"[bold]Bootstrap credentials configured in:[/bold] {credentials_config.as_posix()}")

    if not _credentials_are_valid(profile=profile_name):
        logger.error("Invalid bootstrap credentials. Please check the given keys.")
        return

    accounts = project_config.get("organization").get("accounts")
    management_account = next((account for account in accounts if account["name"] == "management"), None)
    if management_account:
        logger.info("Fetching management account id.")
        management_account["id"] = _get_management_account_id(profile=profile_name)

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


def _get_mfa_serial(profile):
    """ Get MFA serial for the given profile credentials.

    Args:
        profile (str): Name of profile.

    Returns:
        str: MFA device serial.
    """
    _, mfa_devices = awscli(f"--output json iam list-mfa-devices --profile {profile}")
    mfa_devices = json.loads(mfa_devices)

    # Either zero or one MFA device should be configured for either `management` or `security` accounts users.
    # Just for safety, and because we only support VirtualMFA devices, we check that the `SerialNumber` is an `arn`
    # https://docs.aws.amazon.com/IAM/latest/APIReference/API_MFADevice.html
    return next((device["SerialNumber"] for device in mfa_devices["MFADevices"] if re.fullmatch(MFA_SERIAL, device["SerialNumber"])), "")


def configure_profile(profile, values):
    """ Set profile in `config` file for AWS cli.

    Args:
        profile (str): Profile name.
        values (dict): Mapping of values to be set in the profile.
    """
    logger.info(f"\tConfiguring profile [bold]{profile}[/bold]")
    for key, value in values.items():
        awscli(f"configure set {key} {value} --profile {profile}")


def configure_accounts_profiles(profile_name, region, organization_accounts, project_accounts):
    """ Set up the required profiles for all accounts to be used with AWS cli. Backup previous profiles.

    Args:
        profile_name (str): Name of the profile to configure.
        region (str): Region.
        organization_accounts (dict): Name and id of all accounts in the organization.
        project_accounts (dict): Name and email of all accounts in project configuration file.
    """
    short_name, profile = profile_name.split("-")

    mfa_serial = None
    if PROFILES[profile]["mfa"]:
        logger.info("Fetching MFA device serial.")
        mfa_serial = _get_mfa_serial(profile_name)
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
              type=click.Path(exists=True, path_type=Path),
              help="Path to AWS cli credentials file.")
@click.option("--only-accounts-profiles",
              is_flag=True,
              help="Only update accounts' profiles, don't change key/secret.")
@pass_state
def update(state, profile, file, only_accounts_profiles):
    """ Update credentials for the given profile.

    Only to be run after having initialized the project credentials. Generate the profiles for all
    accounts in the project attaching MFA serial if the credentials require so.

    Backup previously existent credentials if necessary and update the project configuration file with
    the ids for all accounts.
    """
    project_config = state.project_config

    short_name = project_config.get("short_name") or _ask_for_short_name()
    region = project_config.get("primary_region") or _ask_for_region()

    if not _profile_is_configured(profile=f"{short_name}-bootstrap"):
        logger.error("Credentials haven't been created yet, please run the credentials creation command first.")
        return

    profile = profile or _ask_for_profile()
    profile_name = f"{short_name}-{profile}"

    credentials_dir = AWSCLI_CONFIG_DIR / short_name
    credentials_config = credentials_dir / "credentials"
    profiles_config = credentials_dir / "config"

    already_configured = _profile_is_configured(profile=profile_name)

    if only_accounts_profiles:
        if not already_configured:
            logger.error("Credentials for this profile haven't been configured yet.\n"
                         "Please re-run the command without the [bold]--only-account-profiles[/bold] flag.")
            return

    else:
        if (not already_configured
                or _ask_for_credentials_overwrite(
                    profile=profile,
                    skip_option_title="Skip credentials setup. Only update accounts' profiles.",
                    overwrite_option_title="Overwrite current credentials. Backups will be made."
                )
            ):
            logger.info(f"Configuring [bold]{profile}[/bold] credentials.")
            configure_credentials(profile_name, file, make_backup=already_configured)
            logger.info(f"[bold]{profile.capitalize()} credentials configured in:[/bold] {credentials_config.as_posix()}")

            if not _credentials_are_valid(profile=profile_name):
                logger.error(f"Invalid {profile} credentials. Please check the given keys.")
                return

    project_accounts = project_config.get("organization").get("accounts")
    if _organization_is_created(profile=profile_name) and project_accounts:
        logger.info("Configuring accounts' profiles.")
        project_name = project_config.get("project_name")

        logger.info("Fetching organization accounts.")
        organization_accounts = _get_organization_accounts(profile=profile_name, project_name=project_name)

        configure_accounts_profiles(profile_name, region, organization_accounts, project_accounts)
        logger.info(f"[bold]Account profiles configured in:[/bold] {profiles_config.as_posix()}")

        for account in project_accounts:
            try: # Account in config file may not be already created
                account["id"] = organization_accounts[account["name"]]
            except KeyError:
                continue

        logger.info("Updating project configuration file.")
        YAML().dump(data=project_config, stream=PROJECT_CONFIG)

        # Update common.tfvars if it exists
        try:
            render_file("config/common.tfvars")
        except FileNotFoundError:
            pass

    else:
        logger.info("No organization has been created yet or no accounts were found in project configuration file."
                    " Skipping accounts' profiles configuration.")

    logger.info(f"Finished updating [bold]{profile}[/bold] credentials.")
