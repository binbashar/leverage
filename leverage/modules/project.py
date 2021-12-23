"""
    Module for managing Leverage projects.
"""
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
from leverage.logger import console
from leverage.path import get_root_path
from leverage.path import NotARepositoryError
from leverage._utils import git

from leverage.modules.terraform import run as tfrun

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
try:
    PROJECT_ROOT = Path(get_root_path())
except NotARepositoryError:
    PROJECT_ROOT = Path.cwd()
PROJECT_CONFIG = PROJECT_ROOT / PROJECT_CONFIG_FILE

CONFIG_DIRECTORY = "config"

# TODO: Keep this structure in the project's directory
PROJECT_STRUCTURE = {
    "management": {
        "global": [
            "base-identities",
            "organizations"
        ],
        "primary_region": [
            "base-tf-backend",
            "security-base"
        ]
    },
    "security": {
        "global": [
            "base-identities"
        ],
        "primary_region": [
            "base-tf-backend",
            "security-base"
        ]
    },
    "shared": {
        "global": [
            "base-identities"
        ],
        "primary_region": [
            "base-network",
            "base-tf-backend",
            "security-base"
        ]
    }
}


@click.group()
def project():
    """ Manage a Leverage project. """


@project.command()
def init():
    """ Initializes and gets all the required resources to be able to create a new Leverage project. """

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
        logger.info(f"No project configuration file found. Dropping configuration template [bold]{PROJECT_CONFIG_FILE}[/bold].")
        copy2(src=CONFIG_FILE_TEMPLATE,
              dst=PROJECT_CONFIG_FILE)

    else:
        logger.warning(f"Project configuration file [bold]{PROJECT_CONFIG_FILE}[/bold] already exists in directory.")

    logger.info("Project initialization finished.")


def _copy_account(account, primary_region):
    """ Copy account directory and all its files.

    Args:
        account (str): Account name.
        primary_region (str): Projects primary region.
    """
    (PROJECT_ROOT / account).mkdir()

    # Copy config directory
    copytree(src=TEMPLATE_DIR / account / CONFIG_DIRECTORY,
             dst=PROJECT_ROOT / account / CONFIG_DIRECTORY,
             ignore=IGNORE_PATTERNS)
    # Copy all global layers in account
    for layer in PROJECT_STRUCTURE[account]["global"]:
        copytree(src=TEMPLATE_DIR / account / "global" / layer,
                 dst=PROJECT_ROOT / account / "global" / layer,
                 ignore=IGNORE_PATTERNS)
    # Copy all layers with a region in account
    for layer in PROJECT_STRUCTURE[account]["primary_region"]:
        copytree(src=TEMPLATE_DIR / account / "primary_region" / layer,
                 dst=PROJECT_ROOT / account / primary_region / layer,
                 ignore=IGNORE_PATTERNS)


def _copy_project_template(config):
    """ Copy all files and directories from the Leverage project template to the project directory.
    It excludes al jinja templates as those will be rendered directly to their final location.

    Args:
        config (dict): Project configuration.
    """
    logger.info("Creating project directory structure.")

    # Copy .gitignore file
    copy2(src=TEMPLATE_DIR / ".gitignore",
          dst=PROJECT_ROOT / ".gitignore")

    # Root config directory
    copytree(src=TEMPLATE_DIR / CONFIG_DIRECTORY,
             dst=PROJECT_ROOT / CONFIG_DIRECTORY,
             ignore=IGNORE_PATTERNS)

    # Accounts
    for account in PROJECT_STRUCTURE:
        _copy_account(account=account, primary_region=config["primary_region"])

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
JINJA_ENV = Environment(loader=FileSystemLoader(TEMPLATES_REPO_DIR.as_posix()),
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
        template_location = template_file.relative_to(TEMPLATES_REPO_DIR)

        template = JINJA_ENV.get_template(template_location.as_posix())
        rendered_template = template.render(config)

        rendered_location = template_file.relative_to(source)
        if (rendered_location.parent.name == ""
                or rendered_location.parent.name == CONFIG_DIRECTORY
                or rendered_location.parent.parent.name == "global"):
            rendered_location = destination / rendered_location

        else:
            region_name = template_location.parent.parent.name
            rendered_location = rendered_location.as_posix().replace(region_name, config[region_name])
            rendered_location = destination / Path(rendered_location)

        rendered_location = rendered_location.with_suffix("")

        rendered_location.write_text(rendered_template)


def _render_account_templates(account, config, source=TEMPLATE_DIR):
    account_name = account["name"]
    logger.info(f"Account: Setting up [bold]{account_name}[/bold].")
    account_dir = source / account_name

    layers = [CONFIG_DIRECTORY]
    for account_name, account_layers in PROJECT_STRUCTURE[account_name].items():
        layers = layers + [f"{account_name}/{layer}" for layer in account_layers]

    for layer in layers:
        logger.info(f"\tLayer: Setting up [bold]{layer.split('/')[-1]}[/bold].")
        layer_dir = account_dir / layer

        layer_templates = layer_dir.glob(TEMPLATE_PATTERN)
        _render_templates(template_files=layer_templates,
                          config=config,
                          source=source)


def _render_project_template(config, source=TEMPLATE_DIR):
    # Render base and non account related templates
    template_files = list(source.glob(TEMPLATE_PATTERN))
    config_templates = list((source / CONFIG_DIRECTORY).rglob(TEMPLATE_PATTERN))
    template_files.extend(config_templates)

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
        logger.debug("No project config file found.")
        return {}

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
    _copy_project_template(config=config)

    # Render project
    _render_project_template(config=config)

    # Format the code correctly
    logger.info("Reformatting terraform configuration to the standard style.")
    # NOTE: This is done just for the sake of making sure the docker image is already available,
    # otherwise two animations try to stack on each other and rich does not support that.
    # TODO: Modularize docker handling as to avoid this.
    tfrun(entrypoint="/bin/sh -c", command="'echo \"pull image\"'", enable_mfa=False, interactive=False)
    with console.status("Formatting..."):
        tfrun(command="fmt -recursive", enable_mfa=False, interactive=False)

    logger.info("Finished setting up project.")


def render_file(file, config=None):
    """ Utility to re-render specific files.

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
