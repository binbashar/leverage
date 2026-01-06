from unittest.mock import patch

import pytest

from leverage import leverage
from leverage.modules.tf import has_a_plan_file


@pytest.mark.parametrize(
    "args",
    [
        ([]),
        (["-migrate-state"]),
        (["-r1", "-r2"]),
    ],
)
def test_init_arguments(leverage_project, leverage_runner, args):
    """
    Test that the arguments for the init command are prepared correctly.
    """
    with leverage_runner(leverage_project) as runner:
        with patch("leverage.modules.tfrunner.TFRunner.run", return_value=0) as mocked_run:
            result = runner.invoke(leverage, ["tf", "init", *args])

        # Check that init was called
        assert mocked_run.call_args_list[0][0][0] == "init"

        # Check that backend-config is included with the correct path
        backend_config_path = str(leverage_project / "account" / "config" / "backend.tfvars")
        backend_config_arg = f"-backend-config={backend_config_path}"

        # Build expected args: user args + backend-config
        expected_args = list(args) + [backend_config_arg]
        actual_args = list(mocked_run.call_args_list[0][0][1:])

        assert actual_args == expected_args


def test_init_with_args(leverage_project, leverage_runner):
    """
    Test tf init with arguments.
    """
    with leverage_runner(leverage_project) as runner:
        with patch("leverage.modules.tfrunner.TFRunner.run", return_value=0) as mocked_run:
            result = runner.invoke(leverage, ["tf", "init", "-migrate-state"])

        assert mocked_run.call_args_list[0][0][0] == "init"
        assert mocked_run.call_args_list[0][0][1] == "-migrate-state"
        assert mocked_run.call_args_list[0][0][2] == f"-backend-config={leverage_project / 'account' / 'config' / 'backend.tfvars'}"


@pytest.mark.parametrize(
    "args, expected_output",
    [
        # No arguments, there's no plan file
        ([], False),
        # One argument that doesn't begin with '-', it is a plan file
        (["plan_file"], True),
        # A single flag/mode, no plan file
        (["-no-color"], False),
        # A single argument that has -key=value form, no plan file
        (["-val='NAME=value'"], False),
        # One key value argument, no plan file
        (["-target", "aws_iam_role.example_role"], False),
        # One flag before a plan file
        (["-compact-warnings", "plan_file"], True),
        # One -key=value argument before a plan file
        (["-lock=false", "plan_file"], True),
        # One key value argument before a plan file
        (["-lock-timeout", "5s", "plan_file"], True),
        # Some other options
        (["-no-color", "-auto-approve"], False),
        (["-destroy", "-target", "aws_iam_role.example.role"], False),
        (["-target=aws_iam_role.example_role", "-destroy"], False),
    ],
)
def test_apply_arguments_have_plan_file(args, expected_output):
    assert has_a_plan_file(tuple(args)) == expected_output
