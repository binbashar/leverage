from unittest.mock import patch, Mock

import pytest
from click import get_current_context

from leverage._internals import State
from leverage.container import TerraformContainer
from leverage.modules.terraform import _init
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
