import os

import pytest

from leverage.modules.tfrunner import TFRunner


@pytest.fixture
def mock_tofu_binary(mocker):
    """Mock tofu binary availability"""
    mocker.patch("shutil.which", return_value="/usr/bin/tofu")
    return "/usr/bin/tofu"


@pytest.fixture
def mock_terraform_binary(mocker):
    """Mock terraform binary availability"""
    mocker.patch("shutil.which", return_value="/usr/bin/terraform")
    return "/usr/bin/terraform"


def test_init_defaults_to_opentofu(mock_tofu_binary):
    runner = TFRunner()
    assert runner.binary_input == "tofu"
    assert runner.binary_path == mock_tofu_binary
    assert runner.instance_env_vars == {}


def test_init_with_terraform_flag(mock_terraform_binary):
    runner = TFRunner(terraform=True)
    assert runner.binary_input == "terraform"
    assert runner.binary_path == mock_terraform_binary


def test_init_with_env_vars(mock_tofu_binary):
    env_vars = {"TF_VAR_region": "us-east-1", "TF_LOG": "DEBUG"}
    runner = TFRunner(env_vars=env_vars)
    assert runner.instance_env_vars == env_vars


def test_init_with_terraform_and_env_vars(mock_terraform_binary):
    env_vars = {"TF_VAR_region": "us-west-2"}
    runner = TFRunner(terraform=True, env_vars=env_vars)
    assert runner.binary_input == "terraform"
    assert runner.instance_env_vars == env_vars


def test_init_with_none_env_vars(mock_tofu_binary):
    runner = TFRunner(env_vars=None)
    assert runner.instance_env_vars == {}


def test_opentofu_not_found_error_message(mocker):
    mocker.patch("shutil.which", return_value=None)
    with pytest.raises(RuntimeError) as exc_info:
        TFRunner()

    assert "OpenTofu binary not found" in str(exc_info.value)
    assert TFRunner.OPENTOFU_INSTALL_URL in str(exc_info.value)


def test_terraform_not_found_error_message(mocker):
    mocker.patch("shutil.which", return_value=None)
    with pytest.raises(RuntimeError) as exc_info:
        TFRunner(terraform=True)

    assert "Terraform binary not found" in str(exc_info.value)
    assert TFRunner.TERRAFORM_INSTALL_URL in str(exc_info.value)


def test_run_without_env_vars(mock_tofu_binary, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    runner = TFRunner()
    result = runner.run("plan", "-out=plan.tfplan")

    assert result == 0
    mock_subprocess.assert_called_once_with(
        [mock_tofu_binary, "plan", "-out=plan.tfplan"], env=os.environ.copy(), cwd=None
    )


def test_run_with_instance_env_vars_only(mock_tofu_binary, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    instance_env = {"TF_VAR_region": "us-east-1", "TF_LOG": "DEBUG"}
    expected_env = os.environ.copy()
    expected_env.update(instance_env)

    runner = TFRunner(env_vars=instance_env)
    result = runner.run("apply", "-auto-approve")

    assert result == 0
    mock_subprocess.assert_called_once_with([mock_tofu_binary, "apply", "-auto-approve"], env=expected_env, cwd=None)


def test_run_with_run_env_vars_only(mock_tofu_binary, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    run_env = {"TF_VAR_environment": "production"}
    expected_env = os.environ.copy()
    expected_env.update(run_env)

    runner = TFRunner()
    result = runner.run("plan", env_vars=run_env)

    assert result == 0
    mock_subprocess.assert_called_once_with([mock_tofu_binary, "plan"], env=expected_env, cwd=None)


def test_run_merges_instance_and_run_env_vars(mock_tofu_binary, mocker):
    """Test that TFRunner properly merges env_vars through the parent class"""
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    instance_env = {"TF_VAR_region": "us-east-1", "TF_LOG": "DEBUG"}
    run_env = {"TF_VAR_environment": "production", "TF_VAR_instance_type": "t3.micro"}

    expected_env = os.environ.copy()
    expected_env.update(instance_env)
    expected_env.update(run_env)

    runner = TFRunner(env_vars=instance_env)
    result = runner.run("apply", env_vars=run_env)

    assert result == 0
    mock_subprocess.assert_called_once_with([mock_tofu_binary, "apply"], env=expected_env, cwd=None)


def test_run_env_vars_override_instance_env_vars(mock_tofu_binary, mocker):
    """Test that run-time env_vars override instance env_vars through parent class"""
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    instance_env = {"TF_VAR_region": "us-east-1", "TF_LOG": "DEBUG"}
    run_env = {"TF_VAR_region": "us-west-2"}  # Override region

    expected_env = os.environ.copy()
    expected_env.update({"TF_VAR_region": "us-west-2", "TF_LOG": "DEBUG"})

    runner = TFRunner(env_vars=instance_env)
    result = runner.run("plan", env_vars=run_env)

    assert result == 0
    mock_subprocess.assert_called_once_with([mock_tofu_binary, "plan"], env=expected_env, cwd=None)


def test_run_interactive_false(mock_tofu_binary, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0
    mock_subprocess.return_value.stdout = "terraform output"
    mock_subprocess.return_value.stderr = ""

    runner = TFRunner()
    exit_code, stdout, stderr = runner.run("output", "-json", interactive=False)

    assert exit_code == 0
    assert stdout == "terraform output"
    assert stderr == ""
    mock_subprocess.assert_called_once_with(
        [mock_tofu_binary, "output", "-json"], env=os.environ.copy(), cwd=None, capture_output=True, text=True
    )


def test_run_with_multiple_args(mock_terraform_binary, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    runner = TFRunner(terraform=True)
    result = runner.run("plan", "-var", "region=us-east-1", "-out=plan.tfplan")

    assert result == 0
    mock_subprocess.assert_called_once_with(
        [mock_terraform_binary, "plan", "-var", "region=us-east-1", "-out=plan.tfplan"], env=os.environ.copy(), cwd=None
    )


def test_run_preserves_instance_env_vars_across_multiple_calls(mock_tofu_binary, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    instance_env = {"TF_VAR_region": "us-east-1"}
    expected_env = os.environ.copy()
    expected_env.update(instance_env)

    runner = TFRunner(env_vars=instance_env)

    # First call
    runner.run("init")
    mock_subprocess.assert_called_with([mock_tofu_binary, "init"], env=expected_env, cwd=None)

    # Second call - instance env vars should still be present
    runner.run("plan")
    assert mock_subprocess.call_count == 2
    mock_subprocess.assert_called_with([mock_tofu_binary, "plan"], env=expected_env, cwd=None)


def test_run_does_not_modify_instance_env_vars(mock_tofu_binary, mocker):
    """Test that instance_env_vars are preserved (handled by parent class)"""
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    instance_env = {"TF_VAR_region": "us-east-1"}
    run_env = {"TF_VAR_environment": "production"}

    runner = TFRunner(env_vars=instance_env)
    runner.run("plan", env_vars=run_env)

    # Instance env vars should remain unchanged (verified in parent class)
    assert runner.instance_env_vars == {"TF_VAR_region": "us-east-1"}


def test_empty_dict_for_none_env_vars_on_run(mock_tofu_binary, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    runner = TFRunner()
    runner.run("plan", env_vars=None)

    # Should not raise an error and should pass empty dict
    mock_subprocess.assert_called_once()


def test_env_vars_converted_to_strings_in_run(mock_tofu_binary, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    instance_env = {"TF_VAR_count": 5, "TF_VAR_enabled": True}
    run_env = {"TF_VAR_timeout": 3.14}

    runner = TFRunner(env_vars=instance_env)
    runner.run("plan", env_vars=run_env)

    called_env = mock_subprocess.call_args[1]["env"]
    assert called_env["TF_VAR_count"] == "5"
    assert called_env["TF_VAR_enabled"] == "True"
    assert called_env["TF_VAR_timeout"] == "3.14"
