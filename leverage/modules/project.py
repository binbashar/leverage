"""
    Module for managing Leverage projects.
"""
import re
from pathlib import Path
from shutil import copy2
from shutil import copytree
from shutil import ignore_patterns
from subprocess import run
from subprocess import PIPE

import click
from click.exceptions import Exit
import pkg_resources
from ruamel.yaml import YAML
from jinja2 import Environment
from jinja2 import FileSystemLoader

from leverage import logger
from leverage.logger import console
from leverage.path import get_root_path
from leverage.path import NotARepositoryError

from leverage.modules.terraform import run as tfrun

# Leverage related base definitions
# NOTE: Should LEVERAGE_DIR be a bit more platform agnostic?
LEVERAGE_DIR = Path.home() / ".leverage"
TEMPLATE_DIR = LEVERAGE_DIR / "template"
TEMPLATE_PATTERN = "*.template"
LEVERAGE_TEMPLATE_REPO = "https://github.com/binbashar/le-tf-infra-aws-template.git"
IGNORE_PATTERNS = ignore_patterns(TEMPLATE_PATTERN, ".gitkeep")

# Useful project related definitions
try:
    PROJECT_ROOT = Path(get_root_path())
except NotARepositoryError:
    PROJECT_ROOT = Path.cwd()
PROJECT_CONFIG_FILE = "project.yaml"
PROJECT_CONFIG = PROJECT_ROOT / PROJECT_CONFIG_FILE

ROOT_DIRECTORIES = [
    "config"
]

DEFAULT_ACCOUNT_LAYERS = [
    "config",
    "base-tf-backend"
]
# TODO: Keep this structure in the project's directory
PROJECT_STRUCTURE = {
    "management": [
        "base-identities",
        "organizations",
        "security-base"
    ],
    "security": [
        "base-identities",
        "security-base"
    ],
    "shared": [
        "base-identities",
        "security-base",
        "base-network"
    ]
}


@click.group()
def project():
    """ Manage a Leverage project. """


@project.command()
def init():
    """ Initializes and gets all the required resources to be able to create a new Leverage project. """

    # Application's directory
    if not LEVERAGE_DIR.exists():
        logger.info("No [bold].leverage[/bold] directory found in user's home. Creating.")
        LEVERAGE_DIR.mkdir()

    # Leverage project template
    if not TEMPLATE_DIR.exists():
        TEMPLATE_DIR.mkdir()

    if not (TEMPLATE_DIR / ".git").exists():
        logger.info("No project template found. Cloning template.")
        run(["git", "clone", LEVERAGE_TEMPLATE_REPO, TEMPLATE_DIR.as_posix()],
            stdout=PIPE, stderr=PIPE, check=True)
        logger.info("Finished cloning template.")

    # Leverage projects are git repositories too
    logger.info("Initializing git repository in project directory.")
    run(["git", "init"], stdout=PIPE, stderr=PIPE, check=True)

    # Project configuration file
    if not PROJECT_CONFIG.exists():
        logger.info("No project configuration file found. Creating an example config.")
        # TODO: Add wizard for the configuration file
        config_example = pkg_resources.resource_string(__name__, PROJECT_CONFIG_FILE)
        PROJECT_CONFIG.write_text(config_example.decode("utf-8"))

    else:
        logger.warning(f"Project configuration file [bold]{PROJECT_CONFIG_FILE}[/bold] already exists in directory.")

    logger.info("Project initialization finished.")


def _copy_account(account):
    """ Copy account directory and all its files.

    Args:
        account (str): Account name.
    """
    account_layers = DEFAULT_ACCOUNT_LAYERS + PROJECT_STRUCTURE[account]

    (PROJECT_ROOT / account).mkdir()

    for layer in account_layers:
        copytree(src=TEMPLATE_DIR / account / layer,
                 dst=PROJECT_ROOT / account / layer,
                 ignore=IGNORE_PATTERNS)


def _copy_project_template():
    """ Copy all files and directories from the Leverage project template to the project directory.
    It excludes al jinja templates as those will be rendered directly to their final location.
    """
    # TODO: Set the project template version (checkout the corresponding tag) based on the
    # project configuration file (under meta.version)
    logger.info("Creating project directory structure.")

    # Copy root files and directories.
    template_regex = re.compile(r".+\.template")
    template_root_files = [file
                           for file in TEMPLATE_DIR.glob("*")
                           if file.is_file() and not template_regex.match(file.name)]

    for directory in ROOT_DIRECTORIES:
        copytree(src=TEMPLATE_DIR / directory,
                 dst=PROJECT_ROOT / directory,
                 ignore=IGNORE_PATTERNS)

    for file in template_root_files:
        copy2(src=file,
              dst=PROJECT_ROOT / file.name)

    # Accounts
    for account in PROJECT_STRUCTURE:
        _copy_account(account=account)

    logger.info("Finished creating directory structure.")


def value(dictionary, key):
    """ Utility function to be used as jinja filter, to ease extraction of values from dictionaries,
    which is sometimes necessary.

    Args:
        dictionary (dict): The dictionary from which a value is to be extracted
        key (str): Key corresponding to the value to be extracted

    Returns:
        any: The value stored in the key
    """
    return dictionary[key]


# Jinja environment used for rendering the templates
JINJA_ENV = Environment(loader=FileSystemLoader(TEMPLATE_DIR.as_posix()),
                        trim_blocks=False,
                        lstrip_blocks=False)
JINJA_ENV.filters["value"] = value


def _render_templates(template_files, config, source=TEMPLATE_DIR, destination=PROJECT_ROOT):
    """ Render the given templates using the given configuration values.

    Args:
        template_files (iterable(Path)): Iterable containing the Path objects corresponding to the
            templates to render.
        config (dict): Values to replace in the templates.
        source (Path, optional): Source directory of the templates. Defaults to TEMPLATE_DIR.
        destination (Path, optional): Destination where to render the templates. Defaults to PROJECT_ROOT.
    """
    for template_file in template_files:
        template_location = template_file.relative_to(source)

        template = JINJA_ENV.get_template(template_location.as_posix())
        rendered_template = template.render(config)

        rendered_location = destination / template_location.with_suffix("")
        rendered_location.write_text(rendered_template)


def _render_account_templates(account, config, source=TEMPLATE_DIR):
    account_name = account["name"]
    logger.info(f"Account: Setting up [bold]{account_name}[/bold].")
    account_dir = source / account_name
    account_layers = DEFAULT_ACCOUNT_LAYERS + PROJECT_STRUCTURE[account_name]

    for layer in account_layers:
        logger.info(f"\tLayer: Setting up [bold]{layer}[/bold].")
        layer_dir = account_dir / layer

        layer_templates = layer_dir.glob(TEMPLATE_PATTERN)
        _render_templates(template_files=layer_templates,
                           config=config,
                           source=source)


def _render_project_template(config, source=TEMPLATE_DIR):
    # Render base and non account related templates
    template_files = list(source.glob(TEMPLATE_PATTERN))
    for directory in ROOT_DIRECTORIES:
        directory_templates = list((source / directory).rglob(TEMPLATE_PATTERN))
        template_files.extend(directory_templates)

    logger.info("Setting up common base files.")
    _render_templates(template_files=template_files,
                      config=config,
                      source=source)

    # Render each account's templates
    for account in config["organization"]["accounts"]:
        _render_account_templates(account=account,
                                  config=config,
                                  source=source)

    logger.info("Project configuration finished.")


def load_project_config():
    """ Load project configuration file.

    Raises:
        Exit: For any error produced during configuration loading.

    Returns:
        dict:  Project configuration.
    """
    if not PROJECT_CONFIG.exists():
        return {}

    logger.info("Loading configuration file.")
    try:
        return YAML().load(PROJECT_CONFIG)

    except Exception as exc:
        exc.__traceback__ = None
        logger.exception(message="Error loading configuration file.", exc_info=exc)
        raise Exit(1)


@project.command()
def create():
    """ Create the directory structure required by the project configuration and set up each account accordingly. """

    config = load_project_config()
    if not config:
        logger.error("No configuration file found for the project."
                     " Make sure the project has already been initialized ([bold]leverage project init[/bold]).")
        return

    if (PROJECT_ROOT / "config").exists():
        logger.error("Project has already been created.")
        return

    # Make project structure
    _copy_project_template()

    # Render project
    _render_project_template(config=config)

    # Format the code correctly
    logger.info("Reformatting terraform configuration to the standard style.")
    with console.status("Formatting..."):
        tfrun(command="fmt -recursive", enable_mfa=False, interactive=False)

    logger.info("Finished setting up project.")


def render_file(file):
    """ Utility to re-render specific files.

    Args:
        file (str): Relative path to file to render.

    Returns:
        bool: Whether the action succeeded or not
    """
    # TODO: Make use of internal state
    config = load_project_config()
    if not config:
        return False

    _render_templates([TEMPLATE_DIR / f"{file}.template"], config=config)

    return True
