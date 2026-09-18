from pathlib import Path
from unittest.mock import patch

import click
import pytest

from leverage import conf
from leverage import leverage
from leverage import path as lepath
from leverage._internals import State
from leverage.path import PathsHandler
from leverage.modules.tf import _validate_layout, has_a_plan_file


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
            runner.invoke(leverage, ["tf", "init", *args])

    called_args = list(mocked_run.call_args_list[0][0])

    # Check that init was called
    assert called_args[0] == "init"

    # The layer tfvars are injected before the user arguments. They are discovered by globbing
    # the config directories, so their order depends on the filesystem and cannot be asserted.
    assert {arg for arg in called_args if arg.startswith("-var-file=")} == {
        f"-var-file={(leverage_project / 'config' / 'common.tfvars').as_posix()}",
        f"-var-file={(leverage_project / 'account' / 'config' / 'account.tfvars').as_posix()}",
        f"-var-file={(leverage_project / 'account' / 'config' / 'backend.tfvars').as_posix()}",
    }

    # Check that the user arguments are preserved and backend-config is appended last
    backend_config_arg = f"-backend-config={leverage_project / 'account' / 'config' / 'backend.tfvars'}"
    remaining_args = [arg for arg in called_args[1:] if not arg.startswith("-var-file=")]

    assert remaining_args == [*args, backend_config_arg]


def test_init_with_args(leverage_project, leverage_runner):
    """
    Test tf init with arguments.
    """
    with leverage_runner(leverage_project) as runner:
        with patch("leverage.modules.tfrunner.TFRunner.run", return_value=0) as mocked_run:
            runner.invoke(leverage, ["tf", "init", "-migrate-state"])

    called_args = list(mocked_run.call_args_list[0][0])

    # User arguments are placed after the layer tfvars and before the backend configuration
    assert called_args[0] == "init"
    assert called_args[-2] == "-migrate-state"
    assert called_args[-1] == f"-backend-config={leverage_project / 'account' / 'config' / 'backend.tfvars'}"


def test_validate_layout_checks_the_given_layer_not_cwd(leverage_project, monkeypatch):
    """
    Regression test: `_validate_layout` must validate the *layer* it was given, not `paths.cwd`.
    Otherwise `leverage tf init --layers a,b` run from an account-level "layers-group" directory
    (e.g. account/us-east-1) always fails with "This command can only run at layer level.",
    since cwd itself - the layers-group - has no .tf files of its own, only its layer
    subdirectories do.
    """
    layers_group = leverage_project / "account" / "us-east-1"
    layer = layers_group / "security-base"

    monkeypatch.setattr(Path, "cwd", lambda: layers_group)
    monkeypatch.setattr(lepath, "get_working_path", lambda: layers_group)
    monkeypatch.setattr(lepath, "get_root_path", lambda: leverage_project)
    monkeypatch.setattr(conf, "get_root_path", lambda: leverage_project)
    monkeypatch.setattr(conf, "get_working_path", lambda: layers_group)

    state = State()
    state.verbosity = False
    state.config = conf.load()
    state.paths = PathsHandler(state.config)

    with click.Context(command=click.Command("leverage"), obj=state):
        # Must not raise ExitError("This command can only run at layer level."), which it would
        # if check_for_layer_location() fell back to checking cwd (the layers-group) instead.
        _validate_layout(layer)


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
