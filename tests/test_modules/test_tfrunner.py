import os

import pytest

from leverage.modules.tfrunner import TFRunner
from leverage._utils import ExitError


@pytest.fixture
def mock_tofu_binary(mocker):
    """Mock tofu binary availability and version check"""
    mocker.patch("shutil.which", return_value="/usr/bin/tofu")
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.stdout = "OpenTofu v1.6.0"
    return "/usr/bin/tofu"


@pytest.fixture
def mock_terraform_binary(mocker):
    """Mock terraform binary availability and version check"""
    mocker.patch("shutil.which", return_value="/usr/bin/terraform")
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.stdout = "Terraform v1.6.0"
    return "/usr/bin/terraform"


def test_init_defaults_to_opentofu(mock_tofu_binary):
    runner = TFRunner(binary="")
    assert runner.binary_input == "tofu"
    assert runner.binary_path == mock_tofu_binary
    assert runner.instance_env_vars == {}


def test_init_with_terraform_flag(mock_terraform_binary):
    runner = TFRunner(binary="", terraform=True)
    assert runner.binary_input == "terraform"
    assert runner.binary_path == mock_terraform_binary


def test_opentofu_not_found_error_message(mocker):
    mocker.patch("shutil.which", return_value=None)
    with pytest.raises(ExitError) as exc_info:
        TFRunner(binary="")

    assert "OpenTofu binary not found" in str(exc_info.value)
    assert TFRunner.OPENTOFU_INSTALL_URL in str(exc_info.value)


def test_terraform_not_found_error_message(mocker):
    mocker.patch("shutil.which", return_value=None)
    with pytest.raises(ExitError) as exc_info:
        TFRunner(binary="", terraform=True)

    assert "Terraform binary not found" in str(exc_info.value)
    assert TFRunner.TERRAFORM_INSTALL_URL in str(exc_info.value)


def test_validate_binary_wrong_binary_for_opentofu(mocker):
    """Test that using Terraform binary when expecting OpenTofu raises an error"""
    mocker.patch("shutil.which", return_value="/usr/bin/terraform")
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.stdout = "Terraform v1.6.0\non linux_amd64"

    with pytest.raises(ExitError) as exc_info:
        TFRunner(binary="")

    assert "does not seem to be OpenTofu" in str(exc_info.value)


def test_validate_binary_wrong_binary_for_terraform(mocker):
    """Test that using OpenTofu binary when expecting Terraform raises an error"""
    mocker.patch("shutil.which", return_value="/usr/bin/tofu")
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.stdout = "OpenTofu v1.6.0\non linux_amd64"

    with pytest.raises(ExitError) as exc_info:
        TFRunner(binary="", terraform=True)

    assert "does not seem to be Terraform" in str(exc_info.value)


def test_run_without_env_vars(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/tofu")
    mock_subprocess = mocker.patch("subprocess.run")
    # First call is for --version validation, second is for actual run
    mock_subprocess.return_value.stdout = "OpenTofu v1.6.0"
    mock_subprocess.return_value.returncode = 0

    runner = TFRunner(binary="")
    result = runner.run("plan", "-out=plan.tfplan")

    assert result == 0
    # Check the last call (the actual run, not the --version check)
    assert mock_subprocess.call_args[0][0] == ["/usr/bin/tofu", "plan", "-out=plan.tfplan"]
    assert mock_subprocess.call_args[1]["env"] == os.environ.copy()
    assert mock_subprocess.call_args[1]["cwd"] is None
    assert mock_subprocess.call_args[1]["capture_output"] is False
    assert mock_subprocess.call_args[1]["text"] is False


def test_exec_does_not_raise_by_default(mock_tofu_binary, mocker):
    """Unlike Runner.exec: callers of TFRunner.exec check the exit code themselves."""
    runner = TFRunner(binary="")
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 1
    mock_subprocess.return_value.stdout = ""
    mock_subprocess.return_value.stderr = "Error: no configuration files"

    assert runner.exec("output") == (1, "", "Error: no configuration files")
