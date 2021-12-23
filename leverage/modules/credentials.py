"""
    Credentials managing module.
"""
import re
import csv
import json
from pathlib import Path
from functools import wraps

import hcl2
import click
from click.exceptions import Exit
import questionary
from questionary import Choice
from ruamel.yaml import YAML

from leverage import logger
from leverage.path import get_root_path
from leverage.path import get_global_config_path
from leverage.path import NotARepositoryError
from leverage.modules.terraform import awscli
from leverage.modules.terraform import run as tfrun
from leverage.modules.project import PROJECT_CONFIG
from leverage.modules.project import load_project_config
from leverage.conf import ENV_CONFIG_FILE
from leverage.conf import load as load_env_config


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

# TODO: Remove these and get them into the global app state
try:
    PROJECT_COMMON_TFVARS = Path(get_global_config_path())
    PROJECT_ENV = Path(get_root_path())
except NotARepositoryError:
    PROJECT_COMMON_TFVARS = PROJECT_ENV = Path.cwd()

PROJECT_COMMON_TFVARS = PROJECT_COMMON_TFVARS / "common.tfvars"
PROJECT_ENV_CONFIG = PROJECT_ENV / ENV_CONFIG_FILE
AWSCLI_CONFIG_DIR = Path.home() / ".aws"

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
        message="Project short name:",
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
        message="Credentials default region:",
        qmark=">",
        default="us-east-1",
        validate=lambda value: bool(re.fullmatch(REGION, value)) or "Invalid region."
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
            "validate": lambda value: (Path(value).expanduser().is_file() and Path(value).expanduser().exists()) or "Path must be an existing file"
        }
    ])
    if not location:
        return

    input_type = location.get("input_type")
    return Path(location.get("path")).expanduser() if input_type == "path" else input_type


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
def credentials():
    """ Manage AWS cli credentials. """


def _load_configs_for_credentials():
    """ Load all required values to configure credentials.

    Raises:
        Exit: If no project has been already initialized in the system.

    Returns:
        dict: Values needed to configure a credential and update the files accordingly.
    """
    logger.info("Loading configuration file.")
    project_config = load_project_config()

    logger.info("Loading project environment configuration file.")
    env_config = load_env_config()

    terraform_config = {}
    if PROJECT_COMMON_TFVARS.exists():
        logger.info("Loading Terraform common configuration.")
        terraform_config = hcl2.loads(PROJECT_COMMON_TFVARS.read_text())

    config_values = {}
    config_values["short_name"] = (project_config.get("short_name")
                                       or env_config.get("PROJECT")
                                       or terraform_config.get("project")
                                       or _ask_for_short_name())
    config_values["project_name"] = (project_config.get("project_name")
                                         or terraform_config.get("project_long"))

    config_values["primary_region"] = (project_config.get("primary_region")
                                           or terraform_config.get("region_primary")
                                           or _ask_for_region())
    config_values["secondary_region"] = terraform_config.get("region_secondary")

    config_values["organization"] = {"accounts": []}
    # Accounts defined in Terraform code take priority
    terraform_accounts = terraform_config.get("accounts", {})
    if terraform_accounts:
        config_values["organization"]["accounts"].extend([
            {
                "name": account_name,
                "email": account_info.get("email"),
                "id": account_info.get("id")
            }
            for account_name, account_info in terraform_accounts.items()
        ])
    # Add accounts not found in terraform code
    project_accounts = [
        account for account in project_config.get("organization", {}).get("accounts", [])
        if account.get("name") not in terraform_accounts
    ]
    if project_accounts:
        config_values["organization"]["accounts"].extend(project_accounts)

    config_values["mfa_enabled"] = env_config.get("MFA_ENABLED", "false")
    config_values["terraform_image_tag"] = env_config.get("TERRAFORM_IMAGE_TAG", "1.0.9")

    return config_values


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
    with open(file) as access_keys_file:
        try:
            keys = next(csv.DictReader(access_keys_file))

        except csv.Error:
            click.echo("\nMalformed access keys file\n")
            raise Exit(1)

    try:
        access_key_id = keys["Access key ID"]
        secret_access_key = keys["Secret access key"]

    except KeyError:
        click.echo("\nFields for keys not found in access keys file\n")
        raise Exit(1)

    if not re.match(KEY_ID, access_key_id) or not re.match(SECRET_KEY, secret_access_key):
        click.echo("\nMalformed keys in access keys file\n")
        raise Exit(1)

    return access_key_id, secret_access_key


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


def _get_organization_accounts(profile, project_name):
    """ Get organization accounts names and ids. Removing the prefixed project name from the account names.

    Args:
        profile (str): Credentials profile.
        project_name (str): Full name of the project.

    Returns:
        dict: Mapping of organization accounts names to ids.
    """
    exit_code, organization_accounts = awscli(f"--output json organizations list-accounts --profile {profile}")

    if exit_code:
        return {}

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


def configure_accounts_profiles(profile, region, organization_accounts, project_accounts):
    """ Set up the required profiles for all accounts to be used with AWS cli. Backup previous profiles.

    Args:
        profile(str): Name of the profile to configure.
        region (str): Region.
        organization_accounts (dict): Name and id of all accounts in the organization.
        project_accounts (dict): Name and email of all accounts in project configuration file.
    """
    short_name, type = profile.split("-")

    mfa_serial = ""
    if PROFILES[type]["mfa"]:
        logger.info("Fetching MFA device serial.")
        mfa_serial = _get_mfa_serial(profile)
        if not mfa_serial:
            logger.error("No MFA device found for user. Please set up a device before configuring the accounts profiles.")
            raise Exit(1)

    account_profiles = {}
    for account in project_accounts:
        account_name = account["name"]
        # DevOps roles do not have permission over management account
        if "security" in profile and account_name == "management":
            continue

        # TODO: Add remaining profiles for remaining accounts declared in code if enough information is available
        account_id = organization_accounts.get(account_name, account.get("id"))
        if account_id is None:
            continue

        # A profile identifier looks like `le-security-oaar`
        account_profiles[f"{short_name}-{account_name}-{PROFILES[type]['profile_role']}"] = {
            "output": "json",
            "region": region,
            "role_arn": f"arn:aws:iam::{account_id}:role/{PROFILES[type]['role']}",
            "source_profile": profile,
            "mfa_serial": mfa_serial
        }

    logger.info("Backing up account profiles file.")
    _backup_file("config")

    for profile_identifier, profile_values in account_profiles.items():
        configure_profile(profile_identifier, profile_values)


def _update_account_ids(config):
    """ Update accounts ids in global configuration file.
    It updates both `[account name]_account_id` and `accounts` variables.
    This last one maintaning the format:
    ```
    account = {
      account_name = {
        email = account_email,
        id = account_id
      }
    }
    ```

    Args:
        config (dict): Project configuration values.
    """
    if not PROJECT_COMMON_TFVARS.exists():
        return

    accs = []
    for account in config["organization"]["accounts"]:
        acc_name, acc_email, acc_id = account.values()

        acc = [f"\n    email = \"{acc_email}\""]
        if acc_id:
            tfrun(entrypoint="hcledit",
                command=f"-f /common-config/common.tfvars -u attribute set {acc_name}_account_id \"{acc_id}\"",
                enable_mfa=False,
                interactive=False)

            acc.append(f"    id = {acc_id}")
        acc = ",\n".join(acc)

        accs.append(f"\n  {acc_name} = {{{acc}\n  }}")

    accs = ",".join(accs)
    accs = f"{{{accs}\n}}"

    tfrun(entrypoint="hcledit",
          command=f"-f /common-config/common.tfvars -u attribute set accounts '{accs}'",
          enable_mfa=False,
          interactive=False)


def mutually_exclusive(context, param, value):
    """ Callback for command options --overwrite-existing-credentials and --skip-access-keys-setup mutual exclusivity verification. """
    me_option = {
        "overwrite_existing_credentials": "skip_access_keys_setup",
        "skip_access_keys_setup": "overwrite_existing_credentials"
    }

    if value and context.params.get(me_option[param.name], False):
        raise click.BadOptionUsage(option_name=param,
                                   message=(f"Option {param.opts[0]} is mutually exclusive"
                                            f" with option --{me_option[param.name].replace('_', '-')}."),
                                   ctx=context)

    return value


@credentials.command()
@click.option("--type",
              type=click.Choice(["BOOTSTRAP",
                                 "MANAGEMENT",
                                 "SECURITY"],
                                case_sensitive=False),
              required=True,
              help="Type of credentials to set.")
@click.option("--credentials-file",
              type=click.Path(exists=True, path_type=Path),
              help="Path to AWS cli credentials file.")
@click.option("--overwrite-existing-credentials",
              is_flag=True,
              callback=mutually_exclusive,
              help=("Overwrite existing credentials if already configured.\n"
                    "Mutually exclusive with --skip-access-keys-setup."))
@click.option("--skip-access-keys-setup",
              is_flag=True,
              callback=mutually_exclusive,
              help=("Skip access keys configuration. Continue on with assumable roles setup.\n"
                   "Mutually exclusive with --overwrite-existing-credentials."))
@click.option("--skip-assumable-roles-setup",
              is_flag=True,
              help="Don't configure the accounts assumable roles.")
# TODO: Add --override-role-name parameter for non-default roles in accounts
def configure(type, credentials_file, overwrite_existing_credentials, skip_access_keys_setup, skip_assumable_roles_setup):
    """ Configure credentials for the project.

    It can handle the credentials required for the initial deployment of the project (BOOTSTRAP),
    a management user (MANAGEMENT) or a devops/secops user (SECURITY).
    """
    if skip_access_keys_setup and skip_assumable_roles_setup:
        logger.info("Nothing to do. Exiting.")
        return

    config_values = _load_configs_for_credentials()

    # Environment configuration variables are needed for the Leverage docker container
    if not PROJECT_ENV_CONFIG.exists():
        PROJECT_ENV_CONFIG.write_text(f"PROJECT={config_values['short_name']}")

    type = type.lower()
    short_name = config_values.get("short_name")
    profile = f"{short_name}-{type}"

    already_configured = _profile_is_configured(profile=profile)
    if already_configured and not (skip_access_keys_setup or overwrite_existing_credentials):
        title_extra = "" if skip_assumable_roles_setup else " Continue on with assumable roles setup."

        overwrite_existing_credentials = _ask_for_credentials_overwrite(
            profile=profile,
            skip_option_title=f"Skip credentials configuration.{title_extra}",
            overwrite_option_title="Overwrite current credentials. Backups will be made."
        )

    do_configure_credentials = False if skip_access_keys_setup else overwrite_existing_credentials or not already_configured

    if do_configure_credentials:
        logger.info(f"Configuring [bold]{type}[/bold] credentials.")
        configure_credentials(profile, credentials_file, make_backup=already_configured)
        logger.info(f"[bold]{type.capitalize()} credentials configured in:[/bold]"
                    f" {(AWSCLI_CONFIG_DIR / short_name / 'credentials').as_posix()}")

        if not _credentials_are_valid(profile):
            logger.error(f"Invalid {profile} credentials. Please check the given keys.")
            return

    accounts = config_values.get("organization", {}).get("accounts", False)
    # First time configuring bootstrap credentials
    if type == "bootstrap" and not already_configured:
        management_account = next((account for account in accounts if account["name"] == "management"), None)

        if management_account:
            logger.info("Fetching management account id.")
            management_account_id =_get_management_account_id(profile=profile)
            management_account["id"] = management_account_id

            project_config_file = load_project_config()
            if project_config_file and "accounts" in project_config_file.get("organization", {}):
                project_config_file["organization"]["accounts"] = accounts

                logger.info("Updating project configuration file.")
                YAML().dump(data=project_config_file, stream=PROJECT_CONFIG)

        skip_assumable_roles_setup = True

    profile_for_organization = profile
    # Security credentials don't have permission to access organization information
    if type == "security":
        for type_with_permission in ("management", "bootstrap"):
            profile_to_check = f"{short_name}-{type_with_permission}"

            if _profile_is_configured(profile_to_check):
                profile_for_organization = profile_to_check
                break

    if skip_assumable_roles_setup:
        logger.info("Skipping assumable roles configuration.")

    else:
        logger.info("Attempting to fetch organization accounts.")
        organization_accounts = _get_organization_accounts(profile_for_organization,
                                                           config_values.get("project_name"))
        logger.debug(f"Organization Accounts fetched: {organization_accounts}")

        if organization_accounts or accounts:
            logger.info("Configuring assumable roles.")

            configure_accounts_profiles(profile, config_values["primary_region"], organization_accounts, accounts)
            logger.info(f"[bold]Account profiles configured in:[/bold]"
                        f" {(AWSCLI_CONFIG_DIR / short_name / 'config').as_posix()}")

            for account in accounts:
                try: # Some account may not already be created
                    account["id"] = organization_accounts[account["name"]]
                except KeyError:
                    continue

        else:
            logger.info("No organization has been created yet or no accounts were configured.\n"
                        "Skipping assumable roles configuration.")

    _update_account_ids(config=config_values)
