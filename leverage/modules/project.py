"""
    Module for managing Leverage projects.
"""

import ipaddress
import re
from pathlib import Path
from shutil import copy2
from shutil import copytree
from shutil import ignore_patterns

import click
from click.exceptions import Exit
from ruamel.yaml import YAML
from jinja2 import Environment
from jinja2 import FileSystemLoader

from leverage import logger
from leverage.path import get_project_root_or_current_dir_path
from leverage.path import NotARepositoryError
from leverage.modules.tfrunner import TFRunner
from leverage._utils import git, ExitError

# Leverage related base definitions
LEVERAGE_DIR = Path.home() / ".leverage"
TEMPLATES_REPO_DIR = LEVERAGE_DIR / "templates"
TEMPLATE_DIR = TEMPLATES_REPO_DIR / "template"
PROJECT_CONFIG_FILE = "project.yaml"
TEMPLATE_PATTERN = "*.template"
CONFIG_FILE_TEMPLATE = TEMPLATES_REPO_DIR / "le-resources" / PROJECT_CONFIG_FILE
LEVERAGE_TEMPLATE_REPO = "https://github.com/binbashar/le-tf-infra-aws-template.git"
IGNORE_PATTERNS = ignore_patterns(TEMPLATE_PATTERN, ".gitkeep")

# Useful project related definitions
PROJECT_ROOT = get_project_root_or_current_dir_path()
PROJECT_CONFIG = PROJECT_ROOT / PROJECT_CONFIG_FILE

CONFIG_DIRECTORY = "config"

# project.yaml validation
EMAIL = r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$"
HCL_IDENTIFIER = r"^[a-zA-Z_][a-zA-Z0-9_-]*$"
SCP_POLICY = r"^aws_organizations_policy\.[a-zA-Z_][a-zA-Z0-9_-]*$"
NETWORK_FIELDS = (
    "cidr_block",
    "availability_zones",
    "private_subnets_cidr",
    "private_subnets",
    "public_subnets_cidr",
    "public_subnets",
)

# TODO: Keep this structure in the project's directory
PROJECT_STRUCTURE = {
    "management": {
        "global": [
            "organizations",
            "sso",
        ],
        "primary_region": [
            "base-tf-backend",
            "security-base",
        ],
    },
    "security": {
        "global": [],
        "primary_region": [
            "base-tf-backend",
            "security-base",
        ],
    },
    "shared": {
        "global": [],
        "primary_region": [
            "base-network",
            "base-tf-backend",
            "security-base",
        ],
    },
}


@click.group()
def project():
    """Manage a Leverage project."""


@project.command()
def init():
    """Initializes and gets all the required resources to be able to create a new Leverage project."""

    # Application's directory
    if not LEVERAGE_DIR.exists():
        logger.info("No [bold]Leverage[/bold] config directory found in user's home. Creating.")
        LEVERAGE_DIR.mkdir()

    # Leverage project templates
    if not TEMPLATES_REPO_DIR.exists():
        TEMPLATES_REPO_DIR.mkdir(parents=True)

    if not (TEMPLATES_REPO_DIR / ".git").exists():
        logger.info("No project template found. Cloning template.")
        git(f"clone {LEVERAGE_TEMPLATE_REPO} {TEMPLATES_REPO_DIR.as_posix()}")
        logger.info("Finished cloning template.")

    else:
        logger.info("Project template found. Updating.")
        git(f"-C {TEMPLATES_REPO_DIR.as_posix()} checkout master")
        git(f"-C {TEMPLATES_REPO_DIR.as_posix()} pull")
        logger.info("Finished updating template.")

    # Leverage projects are git repositories too
    logger.info("Initializing git repository in project directory.")
    git("init")

    # Project configuration file
    if not PROJECT_CONFIG.exists():
        logger.info(
            f"No project configuration file found. Dropping configuration template [bold]{PROJECT_CONFIG_FILE}[/bold]."
        )
        copy2(src=CONFIG_FILE_TEMPLATE, dst=PROJECT_CONFIG_FILE)

    else:
        logger.warning(f"Project configuration file [bold]{PROJECT_CONFIG_FILE}[/bold] already exists in directory.")

    logger.info("Project initialization finished.")


def _copy_account(account, primary_region):
    """Copy account directory and all its files.

    Args:
        account (str): Account name.
        primary_region (str): Projects primary region.
    """
    (PROJECT_ROOT / account).mkdir()

    # Copy config directory
    copytree(
        src=TEMPLATE_DIR / account / CONFIG_DIRECTORY,
        dst=PROJECT_ROOT / account / CONFIG_DIRECTORY,
        ignore=IGNORE_PATTERNS,
    )
    # Copy all global layers in account
    for layer in PROJECT_STRUCTURE[account]["global"]:
        copytree(
            src=TEMPLATE_DIR / account / "global" / layer,
            dst=PROJECT_ROOT / account / "global" / layer,
            ignore=IGNORE_PATTERNS,
            symlinks=True,
        )
    # Copy all layers with a region in account
    for layer in PROJECT_STRUCTURE[account]["primary_region"]:
        copytree(
            src=TEMPLATE_DIR / account / "primary_region" / layer,
            dst=PROJECT_ROOT / account / primary_region / layer,
            ignore=IGNORE_PATTERNS,
            symlinks=True,
        )


def _copy_project_template(config):
    """Copy all files and directories from the Leverage project template to the project directory.
    It excludes al jinja templates as those will be rendered directly to their final location.

    Args:
        config (dict): Project configuration.
    """
    logger.info("Creating project directory structure.")

    # Copy .gitignore file
    copy2(src=TEMPLATE_DIR / ".gitignore", dst=PROJECT_ROOT / ".gitignore")

    # Root config directory
    copytree(src=TEMPLATE_DIR / CONFIG_DIRECTORY, dst=PROJECT_ROOT / CONFIG_DIRECTORY, ignore=IGNORE_PATTERNS)

    # Accounts
    for account in PROJECT_STRUCTURE:
        _copy_account(account=account, primary_region=config["primary_region"])

    logger.info("Finished creating directory structure.")


def value(dictionary, key):
    """Utility function to be used as jinja filter, to ease extraction of values from dictionaries,
    which is sometimes necessary.

    Args:
        dictionary (dict): The dictionary from which a value is to be extracted
        key (str): Key corresponding to the value to be extracted

    Returns:
        any: The value stored in the key
    """
    return dictionary[key]


# Jinja environment used for rendering the templates
JINJA_ENV = Environment(loader=FileSystemLoader(TEMPLATES_REPO_DIR.as_posix()), trim_blocks=False, lstrip_blocks=False)
JINJA_ENV.filters["value"] = value


def _render_templates(template_files, config, source=TEMPLATE_DIR, destination=None):
    """Render the given templates using the given configuration values.

    Args:
        template_files (iterable(Path)): Iterable containing the Path objects corresponding to the
            templates to render.
        config (dict): Values to replace in the templates.
        source (Path, optional): Source directory of the templates. Defaults to TEMPLATE_DIR.
        destination (Path, optional): Destination where to render the templates. Defaults to PROJECT_ROOT,
            resolved at call time so it always matches the project root the rest of the module is using.
    """
    if destination is None:
        destination = PROJECT_ROOT

    # Optional, an empty value makes the CLI look for `tofu`/`terraform` in PATH
    config.setdefault("tf_binary", "")

    for template_file in template_files:
        template_location = template_file.relative_to(TEMPLATES_REPO_DIR)

        template = JINJA_ENV.get_template(template_location.as_posix())
        rendered_template = template.render(config)

        rendered_location = template_file.relative_to(source)
        if (
            rendered_location.parent.name == ""
            or rendered_location.parent.name == CONFIG_DIRECTORY
            or rendered_location.parent.parent.name == "global"
        ):
            rendered_location = destination / rendered_location

        else:
            region_name = template_location.parent.parent.name
            rendered_location = rendered_location.as_posix().replace(region_name, config[region_name])
            rendered_location = destination / Path(rendered_location)

        rendered_location = rendered_location.with_suffix("")

        rendered_location.write_text(rendered_template)


def _render_account_templates(account_name, config, source=TEMPLATE_DIR):
    logger.info(f"Account: Setting up [bold]{account_name}[/bold].")
    account_dir = source / account_name

    layers = [CONFIG_DIRECTORY]
    for location, location_layers in PROJECT_STRUCTURE[account_name].items():
        layers = layers + [f"{location}/{layer}" for layer in location_layers]

    for layer in layers:
        logger.info(f"\tLayer: Setting up [bold]{layer.split('/')[-1]}[/bold].")
        layer_dir = account_dir / layer

        layer_templates = layer_dir.glob(TEMPLATE_PATTERN)
        _render_templates(template_files=layer_templates, config=config, source=source)


def _render_project_template(config, source=TEMPLATE_DIR):
    # Render base and non account related templates
    template_files = list(source.glob(TEMPLATE_PATTERN))
    config_templates = list((source / CONFIG_DIRECTORY).rglob(TEMPLATE_PATTERN))
    template_files.extend(config_templates)

    logger.info("Setting up common base files.")
    _render_templates(template_files=template_files, config=config, source=source)

    # Render each account's templates
    for account_name in PROJECT_STRUCTURE:
        _render_account_templates(account_name=account_name, config=config, source=source)

    logger.info("Project configuration finished.")


def load_project_config():
    """Load project configuration file.

    Raises:
        Exit: For any error produced during configuration loading.

    Returns:
        dict:  Project configuration.
    """
    if not PROJECT_CONFIG.exists():
        logger.debug("No project config file found.")
        return {}

    try:
        return YAML().load(PROJECT_CONFIG)

    except Exception as exc:
        exc.__traceback__ = None
        logger.exception(message="Error loading configuration file.", exc_info=exc)
        raise Exit(1)


def validate_config(config: dict):
    """
    Run a battery of validations over the config file (project.yaml).
    """
    if not re.match(r"^[a-z0-9]([a-z0-9]|-){1,23}[a-z0-9]$", config["project_name"]):
        raise ExitError(
            1,
            "Project name is not valid. Only lowercase alphanumeric characters and hyphens are allowed. It must be 25 characters long at most.",
        )

    if not re.match(r"^[a-z]{2,4}$", config["short_name"]):
        raise ExitError(
            1,
            "Project short name is not valid. Only lowercase alphabetic characters are allowed. It must be between 2 and 4 characters long.",
        )

    tf_binary = config.get("tf_binary")
    if tf_binary is not None and not isinstance(tf_binary, str):
        raise ExitError(1, "[bold]tf_binary[/bold] must be the path to the OpenTofu/Terraform binary.")

    _validate_organization_accounts(config)
    _validate_organizational_units(config)
    _validate_shared_network(config)

    return True


def _validate_organization_accounts(config: dict):
    """
    The accounts of the organization must be exactly the ones the project structure is able to create.
    """
    accounts = (config.get("organization") or {}).get("accounts") or []
    if not isinstance(accounts, list) or not all(isinstance(account, dict) for account in accounts):
        raise ExitError(1, "[bold]organization.accounts[/bold] must be a list of accounts with a name and an email.")

    names = [account.get("name") for account in accounts]
    unknown = [str(name) for name in names if name not in PROJECT_STRUCTURE]
    missing = [name for name in PROJECT_STRUCTURE if name not in names]
    duplicated = sorted({str(name) for name in names if names.count(name) > 1})

    if unknown or missing or duplicated:
        raise ExitError(
            1,
            f"The [bold]organization.accounts[/bold] must be exactly: {', '.join(PROJECT_STRUCTURE)}.\n"
            + (f"  Unknown: {', '.join(unknown)}\n" if unknown else "")
            + (f"  Missing: {', '.join(missing)}\n" if missing else "")
            + (f"  Duplicated: {', '.join(duplicated)}\n" if duplicated else "")
            + "Additional accounts can be added once the project has been created.",
        )

    for account in accounts:
        if not re.match(EMAIL, str(account.get("email") or "")):
            raise ExitError(1, f"Invalid or missing email for account [bold]{account['name']}[/bold].")


def _validate_organizational_units(config: dict):
    """
    Every member account (all but management) must belong to exactly one organizational unit, since the
    organizations layer creates each of them under its parent unit.
    """
    organizational_units = (config.get("organization") or {}).get("organizational_units") or []
    if not isinstance(organizational_units, list) or not all(isinstance(unit, dict) for unit in organizational_units):
        raise ExitError(
            1,
            "[bold]organization.organizational_units[/bold] must be a list of units with a name, policy and accounts.",
        )

    parents = {account: [] for account in PROJECT_STRUCTURE if account != "management"}
    unit_names = []
    for unit in organizational_units:
        name = unit.get("name")
        if not isinstance(name, str) or not re.match(HCL_IDENTIFIER, name):
            raise ExitError(1, f"Invalid organizational unit name [bold]{name}[/bold].")
        unit_names.append(name)

        # The organizations layer attaches a single policy per unit
        policies = unit.get("policy")
        if (
            not isinstance(policies, list)
            or len(policies) != 1
            or not isinstance(policies[0], str)
            or not re.match(SCP_POLICY, policies[0])
        ):
            raise ExitError(
                1,
                f"Organizational unit [bold]{name}[/bold] must have a [bold]policy[/bold] list with exactly one "
                "organization policy, e.g. [aws_organizations_policy.default].",
            )

        unit_accounts = unit.get("accounts") or []
        if not isinstance(unit_accounts, list):
            raise ExitError(1, f"The accounts of organizational unit [bold]{name}[/bold] must be a list.")

        for account in unit_accounts:
            if account == "management":
                raise ExitError(1, "The management account can not be part of an organizational unit.")
            if account not in parents:
                raise ExitError(
                    1,
                    f"Organizational unit [bold]{name}[/bold] references unknown account [bold]{account}[/bold]. "
                    f"Valid accounts are: {', '.join(parents)}.",
                )
            parents[account].append(name)

    duplicated = sorted({name for name in unit_names if unit_names.count(name) > 1})
    if duplicated:
        raise ExitError(1, f"Duplicated organizational units: {', '.join(duplicated)}.")

    orphans = [account for account, units in parents.items() if not units]
    multiple = [account for account, units in parents.items() if len(units) > 1]
    if orphans or multiple:
        raise ExitError(
            1,
            "Each account other than management must belong to exactly one organizational unit.\n"
            + (f"  Without unit: {', '.join(orphans)}\n" if orphans else "")
            + (f"  In more than one unit: {', '.join(multiple)}\n" if multiple else ""),
        )


def _validate_shared_network(config: dict):
    """
    Only the network of the shared account can be configured, and it is required by its base-network layer.
    """
    accounts = config.get("accounts") or {}
    if not isinstance(accounts, dict):
        raise ExitError(1, "[bold]accounts[/bold] must be a mapping containing the [bold]shared[/bold] account.")

    unknown = [str(account) for account in accounts if account != "shared"]
    if unknown:
        raise ExitError(
            1,
            f"Only the [bold]shared[/bold] account can be configured under [bold]accounts[/bold]. Found: {', '.join(unknown)}.",
        )

    networks = (accounts.get("shared") or {}).get("networks")
    if not isinstance(networks, list) or not networks or not isinstance(networks[0], dict):
        raise ExitError(1, "[bold]accounts.shared.networks[/bold] must define at least one network.")

    network = networks[0]
    missing = [field for field in NETWORK_FIELDS if not network.get(field)]
    if missing:
        raise ExitError(1, f"The shared account network is missing: {', '.join(missing)}.")

    zones = network["availability_zones"]
    if not isinstance(zones, list) or not all(isinstance(zone, str) and re.match(r"^[a-z]$", zone) for zone in zones):
        raise ExitError(1, "[bold]availability_zones[/bold] must be a list of zone letters, e.g. [a, b].")

    cidrs = [network["cidr_block"], network["private_subnets_cidr"], network["public_subnets_cidr"]]
    for subnets_field in ("private_subnets", "public_subnets"):
        if not isinstance(network[subnets_field], list):
            raise ExitError(1, f"[bold]{subnets_field}[/bold] must be a list of CIDR blocks.")
        cidrs.extend(network[subnets_field])

    for cidr in cidrs:
        try:
            ipaddress.ip_network(str(cidr))
        except ValueError:
            raise ExitError(1, f"Invalid CIDR block [bold]{cidr}[/bold] in the shared account network.")


@project.command()
def create():
    """Create the directory structure required by the project configuration and set up each account accordingly."""

    config = load_project_config()
    if not config:
        logger.error(
            "No configuration file found for the project."
            " Make sure the project has already been initialized ([bold]leverage project init[/bold])."
        )
        return

    if (PROJECT_ROOT / "config").exists():
        logger.error("Project has already been created.")
        return

    validate_config(config)

    # Keep the rendered accounts in the same order as the project structure
    account_order = list(PROJECT_STRUCTURE)
    config["organization"]["accounts"] = sorted(
        config["organization"]["accounts"], key=lambda account: account_order.index(account["name"])
    )

    # Make project structure
    _copy_project_template(config=config)

    # Render project
    _render_project_template(config=config)

    # Format the code correctly
    logger.info("Reformatting configuration to the standard style.")
    # TODO: Get rid of this ugly workaround
    try:
        TFRunner(binary="tofu").run("fmt", "-recursive")
    except ExitError:
        try:
            TFRunner(binary="terraform").run("fmt", "-recursive")
        except ExitError:
            logger.warning(
                "Could not reformat configuration to the standard style."
                "\nPlease run `terraform fmt -recursive` or `tofu fmt -recursive` manually."
            )

    logger.info("Finished setting up project.")


def render_file(file, config=None):
    """Utility to re-render specific files.

    Args:
        file (str): Relative path to file to render.
        config (dict, optional): Config used to render file.

    Returns:
        bool: Whether the action succeeded or not
    """
    if not config:
        # TODO: Make use of internal state
        config = load_project_config()
        if not config:
            return False

    try:
        _render_templates([TEMPLATE_DIR / f"{file}.template"], config=config)
    except FileNotFoundError:
        return False

    return True
