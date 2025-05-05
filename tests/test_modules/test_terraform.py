from unittest.mock import patch, Mock

import pytest
from click import get_current_context

from leverage._internals import State
from leverage.container import TerraformContainer
from leverage.modules.tf import _init
from leverage.modules.tf import has_a_plan_file
from tests.test_containers import container_fixture_factory


@pytest.fixture
def terraform_container(muted_click_context):
    tf_container = container_fixture_factory(TerraformContainer)

    # this is required because of the @pass_container decorator
    ctx = get_current_context()
    state = State()
    state.container = tf_container
    ctx.obj = state

    # assume we are on a valid location
    with patch.object(tf_container.paths, "check_for_layer_location", Mock()):
        yield tf_container


@pytest.mark.parametrize(
    "args, expected_value",
    [
        ([], ["-backend-config=/project/./config/backend.tfvars"]),
        (["-migrate-state"], ["-migrate-state", "-backend-config=/project/./config/backend.tfvars"]),
        (["-r1", "-r2"], ["-r1", "-r2", "-backend-config=/project/./config/backend.tfvars"]),
    ],
)
def test_init_arguments(terraform_container, args, expected_value):
    """
    Test that the arguments for the init command are prepared correctly.
    """
    with patch.object(terraform_container, "start_in_layer", return_value=0) as mocked:
        _init(args)

    assert mocked.call_args_list[0][0][0] == "init"
    assert " ".join(mocked.call_args_list[0][0][1:]) == " ".join(expected_value)


def test_init_with_args(terraform_container):
    """
    Test tf init with arguments.
    """
    # with patch("dockerpty.exec_command") as mocked_pty:
    with patch.object(terraform_container, "start_in_layer", return_value=0) as mocked:
        _init(["-migrate-state"])

    assert mocked.call_args_list[0][0] == ("init", "-migrate-state", "-backend-config=/project/./config/backend.tfvars")


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
