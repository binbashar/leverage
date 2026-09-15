import tempfile
import subprocess
from pathlib import Path

import pytest
import click
from click.testing import CliRunner

from leverage import path as lepath
from leverage import conf
from leverage._internals import State
from leverage._internals import Module
from leverage.logger import _configure_logger, _leverage_logger
from leverage.path import PathsHandler

BUILD_SCRIPTS = Path("./tests/build_scripts/").resolve()
BUILD_SCRIPT = BUILD_SCRIPTS / "simple_build.py"


@pytest.fixture
def dir_structure(monkeypatch, tmp_path):
    root_dir = tmp_path
    leaf_dir = tmp_path / "account" / "config"
    leaf_dir.mkdir(parents=True)

    monkeypatch.setattr(lepath, "get_root_path", lambda: root_dir)
    monkeypatch.setattr(lepath, "get_working_path", lambda: leaf_dir)

    return root_dir, leaf_dir


@pytest.fixture
def click_context():
    def context(verbose=True, build_script_name="build.py"):
        state = State()
        state.verbosity = verbose
        state.module = Module(name=build_script_name)

        return click.Context(command=click.Command("leverage"), obj=state)

    return context


@pytest.fixture
def with_click_context(click_context):
    """Utility fixture to use a default leverage click context without
    the need of a `with` statement."""
    with click_context():
        yield


@pytest.fixture
def muted_click_context(click_context):
    with click_context(verbose=False):
        yield


@pytest.fixture
def propagate_logs():
    _configure_logger(logger=_leverage_logger)
    _leverage_logger.propagate = True


@pytest.fixture
def leverage_project(tmp_path):
    """
    Creates a mock Leverage project directory structure based on leverage-dir-structure.

    Structure:
        bb/
        ├── .git/
        ├── build.env (PROJECT=bb, MFA_ENABLED=false)
        ├── build.py
        ├── config/
        │   ├── common_variables.tf
        │   └── common.tfvars
        └── account/
            ├── config/
            │   ├── account.tfvars
            │   └── backend.tfvars
            ├── global/
            │   ├── sso/
            │   └── organizations/
            └── us-east-1/
                ├── base-tf-backend/
                │   ├── base-tf-backend.tf
                │   └── backend.tfvars
                └── security-base/
                    ├── security-base.tf
                    └── backend.tfvars

    Returns:
        Path: Root directory of the mock project
    """
    # Create root directory
    tmp_path = tmp_path if tmp_path else tempfile.mkdtemp()
    root = tmp_path / "bb"
    root.mkdir(parents=True)

    # Initialize git repository
    subprocess.run(["git", "init"], cwd=root)

    # Create build.env file with specified content
    build_env = root / "build.env"
    build_env.write_text("PROJECT=bb\nMFA_ENABLED=false\n")

    # Create build.py file with specified content
    build_py = root / "build.py"
    build_py.write_text("# Build script\n")

    # Create config directory and files
    config_dir = root / "config"
    config_dir.mkdir()
    (config_dir / "common_variables.tf").write_text("# Common variables\n")
    (config_dir / "common.tfvars").write_text("# Common tfvars\n")

    # Create account directory structure
    account_dir = root / "account"
    account_dir.mkdir()

    # Create account/config
    account_config = account_dir / "config"
    account_config.mkdir()
    (account_config / "account.tfvars").write_text('environment = "account"\n' 'sso_role = "test-sso-role"\n')
    (account_config / "backend.tfvars").write_text(
        'profile = "bb-account-profile"\n'
        'bucket = "bb-account-terraform-backend"\n'
        'dynamodb_table = "bb-account-terraform-backend-lock"\n'
        'region = "us-east-1"\n'
    )

    # Create account/global
    global_dir = account_dir / "global"
    global_dir.mkdir()
    (global_dir / "sso").mkdir()
    (global_dir / "organizations").mkdir()

    # Create account/us-east-1
    us_east_1 = account_dir / "us-east-1"
    us_east_1.mkdir()

    # Create account/us-east-1/base-tf-backend
    base_tf_backend = us_east_1 / "base-tf-backend"
    base_tf_backend.mkdir()
    (base_tf_backend / "base-tf-backend.tf").write_text("# Base TF backend configuration\n")
    (base_tf_backend / "backend.tfvars").write_text("# Backend tfvars\n")

    # Create account/us-east-1/security-base
    security_base = us_east_1 / "security-base"
    security_base.mkdir()
    (security_base / "security-base.tf").write_text("# Security base configuration\n")
    (security_base / "config.tf").write_text(
        "terraform {\n"
        '  backend "s3" {\n'
        '    key = "account/us-east-1/security-base/terraform.tfstate"\n'
        "  }\n"
        "}\n"
    )
    (security_base / "backend.tfvars").write_text(
        'profile = "bb-account-profile"\n'
        'bucket = "bb-account-terraform-backend"\n'
        'dynamodb_table = "bb-account-terraform-backend-lock"\n'
        'region = "us-east-1"\n'
    )

    return root


@pytest.fixture
def leverage_runner(monkeypatch):
    """
    Creates a CliRunner context manager with patched path functions and authentication.

    Usage:
        with leverage_runner(leverage_project) as runner:
            runner.invoke(leverage, ["command", "args"])

    The fixture automatically patches:
    - get_root_path and get_working_path in both leverage.path and leverage.conf
    - Path.cwd() to return the working directory
    - check_sso_token and refresh_layer_credentials to skip authentication
    - TFRunner binary discovery, so the suite does not require tofu to be installed

    Args:
        leverage_directory: Path to the root of the mock project
        working_directory: Optional working directory (defaults to account/us-east-1/security-base)
    """
    from contextlib import contextmanager
    from leverage.modules import tf, auth
    from leverage.modules.tfrunner import TFRunner

    def skip_binary_validation(tf_runner):
        """Accept the binary as is, without looking it up in PATH nor checking its version.

        Tests using this fixture mock the actual execution, and the binary is not necessarily
        installed where the suite runs. `TFRunner` binary discovery is covered on its own in
        tests/test_modules/test_tfrunner.py.
        """
        tf_runner.binary_path = str(tf_runner.binary_input)

    @contextmanager
    def runner(leverage_directory):
        # Determine working directory
        working_directory = Path(leverage_directory) / "account" / "us-east-1" / "security-base"

        # Ensure paths are Path objects
        leverage_directory = Path(leverage_directory)
        working_directory = Path(working_directory)

        # Apply patches to leverage.path module
        monkeypatch.setattr(lepath, "get_root_path", lambda: leverage_directory)
        monkeypatch.setattr(lepath, "get_working_path", lambda: working_directory)
        monkeypatch.setattr(Path, "cwd", lambda: working_directory)

        # Also patch in conf module since it imports these functions directly
        monkeypatch.setattr(conf, "get_root_path", lambda: leverage_directory)
        monkeypatch.setattr(conf, "get_working_path", lambda: working_directory)

        # Patch binary discovery so the tests do not depend on tofu being installed
        monkeypatch.setattr(TFRunner, "_validate_binary", skip_binary_validation)

        # Patch authentication functions to avoid SSO/credential checks
        monkeypatch.setattr(auth, "check_sso_token", lambda *args, **kwargs: None)
        monkeypatch.setattr(auth, "refresh_layer_credentials", lambda *args, **kwargs: None)
        monkeypatch.setattr(auth, "refresh_layer_credentials_mfa", lambda *args, **kwargs: None)

        # Create and yield the CLI runner
        cli_runner = CliRunner()
        yield cli_runner

    return runner


@pytest.fixture
def leverage_context(leverage_project, monkeypatch):
    def context(verbose=True, build_script_name="build.py"):
        # Set current working directory to security-base layer
        working_dir = leverage_project / "account" / "us-east-1" / "security-base"

        # Mock Path.cwd() to return the working directory
        monkeypatch.setattr(Path, "cwd", lambda: working_dir)

        # Update get_working_path to return the security-base directory
        monkeypatch.setattr(lepath, "get_working_path", lambda: working_dir)

        state = State()
        state.verbosity = verbose
        state.module = Module(name=build_script_name)
        state.config = conf.load()
        state.paths = PathsHandler()

        return click.Context(command=click.Command("leverage"), obj=state)

    return context
