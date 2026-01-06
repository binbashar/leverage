import os
import shutil
from pathlib import Path

import pytest

from leverage.modules.runner import Runner
from leverage._utils import ExitError


def test_init_with_valid_binary_in_path(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/python3")
    runner = Runner("python3")
    assert runner.binary_input == "python3"
    assert runner.binary_path == "/usr/bin/python3"
    assert runner.error_message is None


def test_init_with_absolute_path_existing_file(tmp_path):
    binary_file = tmp_path / "test_binary"
    binary_file.touch()
    binary_file.chmod(0o755)

    runner = Runner(binary_file)
    assert runner.binary_input == binary_file
    assert runner.binary_path == str(binary_file)


def test_init_with_absolute_path_non_existing_file(tmp_path, mocker):
    binary_file = tmp_path / "non_existing_binary"

    with pytest.raises(ExitError) as exc_info:
        Runner(binary_file)

    error_msg = str(exc_info.value)
    assert "not found on system" in error_msg
    assert str(binary_file) in error_msg


def test_init_with_binary_not_in_path(mocker):
    mocker.patch("shutil.which", return_value=None)

    with pytest.raises(ExitError) as exc_info:
        Runner("nonexistent")

    error_msg = str(exc_info.value)
    assert "Binary 'nonexistent' not found on system" in error_msg
    assert "Please install nonexistent" in error_msg


def test_init_with_custom_error_message(mocker):
    custom_error = "Custom error message for missing binary"
    mocker.patch("shutil.which", return_value=None)

    with pytest.raises(ExitError) as exc_info:
        Runner("nonexistent", error_message=custom_error)

    error_msg = str(exc_info.value)
    assert error_msg == custom_error


def test_init_logs_error_on_missing_binary(mocker):
    mocker.patch("shutil.which", return_value=None)

    with pytest.raises(ExitError) as exc_info:
        Runner("nonexistent")

    error_msg = str(exc_info.value)
    assert "Binary 'nonexistent' not found on system" in error_msg


def test_validate_version_base_implementation_does_nothing(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/python3")
    runner = Runner("python3")
    # Base implementation should not raise any exceptions
    runner._validate_version()


@pytest.fixture
def mock_runner(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/test_binary")
    return Runner("test_binary")


def test_run_interactive_success(mock_runner, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    result = mock_runner.run("arg1", "arg2", interactive=True)

    assert result == 0
    mock_subprocess.assert_called_once_with(
        ["/usr/bin/test_binary", "arg1", "arg2"], env=os.environ.copy(), cwd=None, capture_output=False, text=False
    )


def test_run_interactive_failure(mock_runner, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 1

    result = mock_runner.run("arg1", interactive=True)

    assert result == 1


def test_run_non_interactive_success(mock_runner, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0
    mock_subprocess.return_value.stdout = "output"
    mock_subprocess.return_value.stderr = "error"

    result = mock_runner.run("arg1", interactive=False)

    assert result == (0, "output", "error")
    mock_subprocess.assert_called_once_with(
        ["/usr/bin/test_binary", "arg1"], env=os.environ.copy(), cwd=None, capture_output=True, text=True
    )


def test_run_with_env_vars(mock_runner, mocker):
    env_vars = {"TEST_VAR": "test_value", "ANOTHER_VAR": 123}
    expected_env = os.environ.copy()
    expected_env.update({"TEST_VAR": "test_value", "ANOTHER_VAR": "123"})

    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    mock_runner.run("arg1", env_vars=env_vars, interactive=True)

    mock_subprocess.assert_called_once_with(
        ["/usr/bin/test_binary", "arg1"], env=expected_env, cwd=None, capture_output=False, text=False
    )


def test_run_with_working_directory(mock_runner, tmp_path, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    mock_runner.run("arg1", working_dir=tmp_path, interactive=True)

    mock_subprocess.assert_called_once_with(
        ["/usr/bin/test_binary", "arg1"], env=os.environ.copy(), cwd=tmp_path, capture_output=False, text=False
    )


def test_run_with_no_args_defaults_to_empty_list(mock_runner, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    mock_runner.run()

    mock_subprocess.assert_called_once_with(
        ["/usr/bin/test_binary"], env=os.environ.copy(), cwd=None, capture_output=False, text=False
    )


def test_run_with_none_args_defaults_to_empty_list(mock_runner, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    mock_runner.run()

    mock_subprocess.assert_called_once_with(
        ["/usr/bin/test_binary"], env=os.environ.copy(), cwd=None, capture_output=False, text=False
    )


def test_run_with_none_env_vars_defaults_to_empty_dict(mock_runner, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    mock_runner.run(env_vars=None)

    mock_subprocess.assert_called_once_with(
        ["/usr/bin/test_binary"], env=os.environ.copy(), cwd=None, capture_output=False, text=False
    )


def test_run_logs_debug_information(mock_runner, tmp_path, mocker):
    mock_logger = mocker.patch("leverage.modules.runner.logger")
    env_vars = {"TEST_VAR": "value"}
    merged_env_vars = {**mock_runner.instance_env_vars, **env_vars}

    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    mock_runner.run("arg1", env_vars=env_vars, working_dir=tmp_path)

    expected_calls = [
        mocker.call(f"[bold cyan]Running command:[/bold cyan] /usr/bin/test_binary arg1"),
        mocker.call(f"Working directory: {tmp_path}"),
        mocker.call(f"Additional environment variables: {merged_env_vars}"),
    ]
    mock_logger.debug.assert_has_calls(expected_calls)


def test_run_logs_current_directory_when_no_working_dir(mock_runner, mocker):
    mock_logger = mocker.patch("leverage.modules.runner.logger")
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0
    mocker.patch("pathlib.Path.cwd", return_value=Path("/current/path"))

    mock_runner.run("arg1")

    mock_logger.debug.assert_any_call("Working directory: /current/path")


def test_repr(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/python3")
    runner = Runner("python3")
    expected = "Runner(binary_input='python3', binary_path='/usr/bin/python3')"
    assert repr(runner) == expected


def test_repr_with_path_object(tmp_path):
    binary_file = tmp_path / "test_binary"
    binary_file.touch()

    runner = Runner(binary_file)
    expected = f"Runner(binary_input='{binary_file}', binary_path='{binary_file}')"
    assert repr(runner) == expected


@pytest.mark.skipif(shutil.which("echo") is None, reason="echo binary not available")
def test_integration_with_echo_interactive():
    runner = Runner("echo")
    result = runner.run("hello", "world", interactive=True)
    assert result == 0


@pytest.mark.skipif(shutil.which("echo") is None, reason="echo binary not available")
def test_integration_with_echo_non_interactive():
    runner = Runner("echo")
    exit_code, stdout, stderr = runner.run("hello", "world", interactive=False)
    assert exit_code == 0
    assert stdout.strip() == "hello world"
    assert stderr == ""


@pytest.mark.skipif(shutil.which("false") is None, reason="false binary not available")
def test_integration_with_failing_command():
    runner = Runner("false")
    result = runner.run(interactive=True)
    assert result == 1


@pytest.mark.skipif(shutil.which("env") is None, reason="env binary not available")
def test_integration_with_environment_variables():
    runner = Runner("env")
    env_vars = {"TEST_RUNNER_VAR": "test_value"}
    exit_code, stdout, stderr = runner.run(env_vars=env_vars, interactive=False)

    assert exit_code == 0
    assert "TEST_RUNNER_VAR=test_value" in stdout


def test_binary_input_as_path_object(tmp_path):
    binary_file = tmp_path / "test_binary"
    binary_file.touch()

    runner = Runner(binary_file)
    assert isinstance(runner.binary_input, Path)
    assert runner.binary_path == str(binary_file)


def test_binary_input_as_string(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/test")
    runner = Runner("test")
    assert isinstance(runner.binary_input, str)
    assert runner.binary_path == "/usr/bin/test"


def test_env_vars_converted_to_strings(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/test")
    runner = Runner("test")

    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    runner.run(env_vars={"INT_VAR": 42, "FLOAT_VAR": 3.14, "BOOL_VAR": True})

    called_env = mock_subprocess.call_args[1]["env"]
    assert called_env["INT_VAR"] == "42"
    assert called_env["FLOAT_VAR"] == "3.14"
    assert called_env["BOOL_VAR"] == "True"


def test_init_with_instance_env_vars(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/test")
    env_vars = {"TEST_VAR": "test_value", "ANOTHER_VAR": "another_value"}
    runner = Runner("test", env_vars=env_vars)
    assert runner.instance_env_vars == env_vars


def test_init_with_none_instance_env_vars(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/test")
    runner = Runner("test", env_vars=None)
    assert runner.instance_env_vars == {}


def test_run_with_instance_env_vars_only(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/test")
    instance_env = {"INST_VAR": "inst_value"}
    expected_env = os.environ.copy()
    expected_env.update(instance_env)

    runner = Runner("test", env_vars=instance_env)

    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    runner.run("arg1")

    mock_subprocess.assert_called_once_with(
        ["/usr/bin/test", "arg1"], env=expected_env, cwd=None, capture_output=False, text=False
    )


def test_run_merges_instance_and_run_env_vars(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/test")
    instance_env = {"INST_VAR": "inst_value", "COMMON_VAR": "instance"}
    run_env = {"RUN_VAR": "run_value", "COMMON_VAR": "runtime"}

    expected_env = os.environ.copy()
    expected_env.update({"INST_VAR": "inst_value", "RUN_VAR": "run_value", "COMMON_VAR": "runtime"})

    runner = Runner("test", env_vars=instance_env)

    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    runner.run("arg1", env_vars=run_env)

    mock_subprocess.assert_called_once_with(
        ["/usr/bin/test", "arg1"], env=expected_env, cwd=None, capture_output=False, text=False
    )


def test_run_env_vars_override_instance_env_vars(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/test")
    instance_env = {"VAR": "instance_value"}
    run_env = {"VAR": "runtime_value"}

    expected_env = os.environ.copy()
    expected_env.update({"VAR": "runtime_value"})

    runner = Runner("test", env_vars=instance_env)

    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    runner.run("arg1", env_vars=run_env)

    mock_subprocess.assert_called_once_with(
        ["/usr/bin/test", "arg1"], env=expected_env, cwd=None, capture_output=False, text=False
    )


def test_instance_env_vars_preserved_across_multiple_runs(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/test")
    instance_env = {"INST_VAR": "inst_value"}
    expected_env = os.environ.copy()
    expected_env.update(instance_env)

    runner = Runner("test", env_vars=instance_env)

    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    # First run
    runner.run("arg1")
    mock_subprocess.assert_called_with(
        ["/usr/bin/test", "arg1"], env=expected_env, cwd=None, capture_output=False, text=False
    )

    # Second run - instance env vars should still be present
    runner.run("arg2")
    assert mock_subprocess.call_count == 2
    mock_subprocess.assert_called_with(
        ["/usr/bin/test", "arg2"], env=expected_env, cwd=None, capture_output=False, text=False
    )


def test_instance_env_vars_not_modified_by_run(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/test")
    instance_env = {"INST_VAR": "inst_value"}
    run_env = {"RUN_VAR": "run_value"}

    runner = Runner("test", env_vars=instance_env)

    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    runner.run("arg1", env_vars=run_env)

    # Instance env vars should remain unchanged
    assert runner.instance_env_vars == {"INST_VAR": "inst_value"}


def test_instance_env_vars_converted_to_strings(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/test")
    instance_env = {"INT_VAR": 42, "FLOAT_VAR": 3.14}

    runner = Runner("test", env_vars=instance_env)

    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0

    runner.run("arg1")

    called_env = mock_subprocess.call_args[1]["env"]
    assert called_env["INT_VAR"] == "42"
    assert called_env["FLOAT_VAR"] == "3.14"


def test_exec_calls_run_with_interactive_false(mock_runner, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0
    mock_subprocess.return_value.stdout = "test output"
    mock_subprocess.return_value.stderr = "test error"

    exit_code, stdout, stderr = mock_runner.exec("arg1", "arg2")

    assert exit_code == 0
    assert stdout == "test output"
    assert stderr == "test error"
    mock_subprocess.assert_called_once_with(
        ["/usr/bin/test_binary", "arg1", "arg2"], env=os.environ.copy(), cwd=None, capture_output=True, text=True
    )


def test_exec_with_env_vars(mock_runner, mocker):
    env_vars = {"TEST_VAR": "test_value"}
    expected_env = os.environ.copy()
    expected_env.update(env_vars)

    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0
    mock_subprocess.return_value.stdout = "output"
    mock_subprocess.return_value.stderr = ""

    exit_code, stdout, stderr = mock_runner.exec("arg1", env_vars=env_vars)

    assert exit_code == 0
    assert stdout == "output"
    assert stderr == ""
    mock_subprocess.assert_called_once_with(
        ["/usr/bin/test_binary", "arg1"], env=expected_env, cwd=None, capture_output=True, text=True
    )


def test_exec_with_working_directory(mock_runner, tmp_path, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0
    mock_subprocess.return_value.stdout = ""
    mock_subprocess.return_value.stderr = ""

    mock_runner.exec("arg1", working_dir=tmp_path)

    mock_subprocess.assert_called_once_with(
        ["/usr/bin/test_binary", "arg1"], env=os.environ.copy(), cwd=tmp_path, capture_output=True, text=True
    )


def test_exec_with_instance_env_vars(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/test")
    instance_env = {"INST_VAR": "inst_value"}
    expected_env = os.environ.copy()
    expected_env.update(instance_env)

    runner = Runner("test", env_vars=instance_env)

    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0
    mock_subprocess.return_value.stdout = "output"
    mock_subprocess.return_value.stderr = ""

    exit_code, stdout, stderr = runner.exec("arg1")

    assert exit_code == 0
    mock_subprocess.assert_called_once_with(
        ["/usr/bin/test", "arg1"], env=expected_env, cwd=None, capture_output=True, text=True
    )


def test_exec_merges_instance_and_run_env_vars(mocker):
    mocker.patch("shutil.which", return_value="/usr/bin/test")
    instance_env = {"INST_VAR": "inst_value"}
    run_env = {"RUN_VAR": "run_value"}

    expected_env = os.environ.copy()
    expected_env.update(instance_env)
    expected_env.update(run_env)

    runner = Runner("test", env_vars=instance_env)

    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0
    mock_subprocess.return_value.stdout = ""
    mock_subprocess.return_value.stderr = ""

    runner.exec("arg1", env_vars=run_env)

    mock_subprocess.assert_called_once_with(
        ["/usr/bin/test", "arg1"], env=expected_env, cwd=None, capture_output=True, text=True
    )


@pytest.mark.skipif(shutil.which("echo") is None, reason="echo binary not available")
def test_integration_exec_with_echo():
    runner = Runner("echo")
    exit_code, stdout, stderr = runner.exec("hello", "world")
    assert exit_code == 0
    assert stdout.strip() == "hello world"
    assert stderr == ""


def test_run_raises_on_failure_when_raises_true(mock_runner, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 1
    mock_subprocess.return_value.stdout = ""
    mock_subprocess.return_value.stderr = "Command failed"

    with pytest.raises(ExitError) as exc_info:
        mock_runner.run("arg1", interactive=False, raises=True)

    assert exc_info.value.exit_code == 1
    assert "Command execution failed: Command failed" in str(exc_info.value)


def test_run_does_not_raise_on_failure_when_raises_false(mock_runner, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 1
    mock_subprocess.return_value.stdout = ""
    mock_subprocess.return_value.stderr = "Command failed"

    result = mock_runner.run("arg1", interactive=False, raises=False)

    assert result == (1, "", "Command failed")


def test_run_does_not_raise_on_success_when_raises_true(mock_runner, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 0
    mock_subprocess.return_value.stdout = "Success output"
    mock_subprocess.return_value.stderr = ""

    result = mock_runner.run("arg1", interactive=False, raises=True)

    assert result == (0, "Success output", "")


def test_raises_ignored_in_interactive_mode(mock_runner, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 1

    # Should return exit code 1, not raise (raises is ignored in interactive mode)
    result = mock_runner.run("arg1", interactive=True, raises=True)

    assert result == 1
    # Verify no exception was raised


def test_exec_raises_by_default(mock_runner, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 1
    mock_subprocess.return_value.stdout = ""
    mock_subprocess.return_value.stderr = "Exec failed"

    with pytest.raises(ExitError) as exc_info:
        mock_runner.exec("arg1")

    assert exc_info.value.exit_code == 1


def test_exec_does_not_raise_when_raises_false(mock_runner, mocker):
    mock_subprocess = mocker.patch("subprocess.run")
    mock_subprocess.return_value.returncode = 1
    mock_subprocess.return_value.stdout = ""
    mock_subprocess.return_value.stderr = "Exec failed"

    exit_code, stdout, stderr = mock_runner.exec("arg1", raises=False)

    assert exit_code == 1
    assert stdout == ""
    assert stderr == "Exec failed"
