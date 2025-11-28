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


def test_init_with_env_vars(mock_tofu_binary):
    env_vars = {"TF_VAR_region": "us-east-1", "TF_LOG": "DEBUG"}
    runner = TFRunner(binary="", env_vars=env_vars)
    assert runner.instance_env_vars == env_vars


def test_init_with_terraform_and_env_vars(mock_terraform_binary):
    env_vars = {"TF_VAR_region": "us-west-2"}
    runner = TFRunner(binary="", terraform=True, env_vars=env_vars)
    assert runner.binary_input == "terraform"
    assert runner.instance_env_vars == env_vars


def test_init_with_none_env_vars(mock_tofu_binary):
    runner = TFRunner(binary="", env_vars=None)
    assert runner.instance_env_vars == {}


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


def test_validate_binary_opentofu_success(mocker):
    """Test that OpenTofu binary is validated correctly"""
    mocker.patch("shutil.which", return_value="/usr/bin/tofu")
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.stdout = "OpenTofu v1.6.0\non linux_amd64"

    runner = TFRunner(binary="")
    # Should not raise an exception
    assert runner.binary_path == "/usr/bin/tofu"


def test_validate_binary_terraform_success(mocker):
    """Test that Terraform binary is validated correctly"""
    mocker.patch("shutil.which", return_value="/usr/bin/terraform")
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.stdout = "Terraform v1.6.0\non linux_amd64"

    runner = TFRunner(binary="", terraform=True)
    # Should not raise an exception
    assert runner.binary_path == "/usr/bin/terraform"


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


def test_run_with_instance_env_vars_only(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/tofu")
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.stdout = "OpenTofu v1.6.0"
    mock_subprocess.return_value.returncode = 0

    instance_env = {"TF_VAR_region": "us-east-1", "TF_LOG": "DEBUG"}
    expected_env = os.environ.copy()
    expected_env.update(instance_env)

    runner = TFRunner(binary="", env_vars=instance_env)
    result = runner.run("apply", "-auto-approve")

    assert result == 0
    # Check the last call (the actual run)
    assert mock_subprocess.call_args[0][0] == ["/usr/bin/tofu", "apply", "-auto-approve"]
    assert mock_subprocess.call_args[1]["env"] == expected_env
    assert mock_subprocess.call_args[1]["cwd"] is None


def test_run_with_run_env_vars_only(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/tofu")
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.stdout = "OpenTofu v1.6.0"
    mock_subprocess.return_value.returncode = 0

    run_env = {"TF_VAR_environment": "production"}
    expected_env = os.environ.copy()
    expected_env.update(run_env)

    runner = TFRunner(binary="")
    result = runner.run("plan", env_vars=run_env)

    assert result == 0
    # Check the last call
    assert mock_subprocess.call_args[0][0] == ["/usr/bin/tofu", "plan"]
    assert mock_subprocess.call_args[1]["env"] == expected_env
    assert mock_subprocess.call_args[1]["cwd"] is None


def test_run_merges_instance_and_run_env_vars(mocker):
    """Test that TFRunner properly merges env_vars through the parent class"""
    mocker.patch("shutil.which", return_value="/usr/bin/tofu")
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.stdout = "OpenTofu v1.6.0"
    mock_subprocess.return_value.returncode = 0

    instance_env = {"TF_VAR_region": "us-east-1", "TF_LOG": "DEBUG"}
    run_env = {"TF_VAR_environment": "production", "TF_VAR_instance_type": "t3.micro"}

    expected_env = os.environ.copy()
    expected_env.update(instance_env)
    expected_env.update(run_env)

    runner = TFRunner(binary="", env_vars=instance_env)
    result = runner.run("apply", env_vars=run_env)

    assert result == 0
    # Check the last call
    assert mock_subprocess.call_args[0][0] == ["/usr/bin/tofu", "apply"]
    assert mock_subprocess.call_args[1]["env"] == expected_env
    assert mock_subprocess.call_args[1]["cwd"] is None


def test_run_env_vars_override_instance_env_vars(mocker):
    """Test that run-time env_vars override instance env_vars through parent class"""
    mocker.patch("shutil.which", return_value="/usr/bin/tofu")
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.stdout = "OpenTofu v1.6.0"
    mock_subprocess.return_value.returncode = 0

    instance_env = {"TF_VAR_region": "us-east-1", "TF_LOG": "DEBUG"}
    run_env = {"TF_VAR_region": "us-west-2"}  # Override region

    expected_env = os.environ.copy()
    expected_env.update({"TF_VAR_region": "us-west-2", "TF_LOG": "DEBUG"})

    runner = TFRunner(binary="", env_vars=instance_env)
    result = runner.run("plan", env_vars=run_env)

    assert result == 0
    # Check the last call
    assert mock_subprocess.call_args[0][0] == ["/usr/bin/tofu", "plan"]
    assert mock_subprocess.call_args[1]["env"] == expected_env
    assert mock_subprocess.call_args[1]["cwd"] is None


def test_run_interactive_false(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/tofu")
    mock_subprocess = mocker.patch("subprocess.run")
    # First call for --version, second for the actual command
    version_output = type("obj", (object,), {"stdout": "OpenTofu v1.6.0", "returncode": 0})()
    run_output = type("obj", (object,), {"stdout": "terraform output", "stderr": "", "returncode": 0})()
    mock_subprocess.side_effect = [version_output, run_output]

    runner = TFRunner(binary="")
    exit_code, stdout, stderr = runner.run("output", "-json", interactive=False)

    assert exit_code == 0
    assert stdout == "terraform output"  # Already stripped
    assert stderr == ""
    # Check the last call (the actual run)
    assert mock_subprocess.call_args[0][0] == ["/usr/bin/tofu", "output", "-json"]
    assert "capture_output" in mock_subprocess.call_args[1]
    assert mock_subprocess.call_args[1]["capture_output"] is True


def test_run_with_multiple_args(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/terraform")
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.stdout = "Terraform v1.6.0"
    mock_subprocess.return_value.returncode = 0

    runner = TFRunner(binary="", terraform=True)
    result = runner.run("plan", "-var", "region=us-east-1", "-out=plan.tfplan")

    assert result == 0
    # Check the last call
    assert mock_subprocess.call_args[0][0] == [
        "/usr/bin/terraform",
        "plan",
        "-var",
        "region=us-east-1",
        "-out=plan.tfplan",
    ]
    assert mock_subprocess.call_args[1]["env"] == os.environ.copy()
    assert mock_subprocess.call_args[1]["cwd"] is None


def test_run_preserves_instance_env_vars_across_multiple_calls(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/tofu")
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.stdout = "OpenTofu v1.6.0"
    mock_subprocess.return_value.returncode = 0

    instance_env = {"TF_VAR_region": "us-east-1"}
    expected_env = os.environ.copy()
    expected_env.update(instance_env)

    runner = TFRunner(binary="", env_vars=instance_env)

    # First call (after --version check)
    runner.run("init")
    # Second call - instance env vars should still be present
    runner.run("plan")

    # Check that we have 3 calls total (1 --version + 2 actual commands)
    assert mock_subprocess.call_count == 3
    # Verify the last call has the right env vars
    assert mock_subprocess.call_args[1]["env"] == expected_env


def test_run_does_not_modify_instance_env_vars(mocker):
    """Test that instance_env_vars are preserved (handled by parent class)"""
    mocker.patch("shutil.which", return_value="/usr/bin/tofu")
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.stdout = "OpenTofu v1.6.0"
    mock_subprocess.return_value.returncode = 0

    instance_env = {"TF_VAR_region": "us-east-1"}
    run_env = {"TF_VAR_environment": "production"}

    runner = TFRunner(binary="", env_vars=instance_env)
    runner.run("plan", env_vars=run_env)

    # Instance env vars should remain unchanged (verified in parent class)
    assert runner.instance_env_vars == {"TF_VAR_region": "us-east-1"}


def test_empty_dict_for_none_env_vars_on_run(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/tofu")
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.stdout = "OpenTofu v1.6.0"
    mock_subprocess.return_value.returncode = 0

    runner = TFRunner(binary="")
    runner.run("plan", env_vars=None)

    # Should not raise an error - check we have 2 calls (--version + actual run)
    assert mock_subprocess.call_count == 2


def test_env_vars_converted_to_strings_in_run(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/tofu")
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.stdout = "OpenTofu v1.6.0"
    mock_subprocess.return_value.returncode = 0

    instance_env = {"TF_VAR_count": 5, "TF_VAR_enabled": True}
    run_env = {"TF_VAR_timeout": 3.14}

    runner = TFRunner(binary="", env_vars=instance_env)
    runner.run("plan", env_vars=run_env)

    called_env = mock_subprocess.call_args[1]["env"]
    assert called_env["TF_VAR_count"] == "5"
    assert called_env["TF_VAR_enabled"] == "True"
    assert called_env["TF_VAR_timeout"] == "3.14"
