from unittest.mock import patch, Mock

import pytest
from click import get_current_context

from leverage._internals import State
from leverage._utils import AwsCredsContainer
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
        # assume we have valid credentials
        with patch.object(AwsCredsContainer, "__enter__", Mock()):
            yield tf_container


def test_init(terraform_container):
    """
    Test happy path.
    """
    live_container = Mock()
    with patch("leverage._utils.LiveContainer.__enter__", return_value=live_container):
        with patch("dockerpty.exec_command") as mocked_pty:
            _init([])

    assert live_container.exec_run.call_args_list[0].args[0] == "mkdir -p /opt/home/.ssh"
    assert live_container.exec_run.call_args_list[1].args[0] == "chown root:root -R /opt/home/.ssh/"
    assert (
        mocked_pty.call_args_list[0].kwargs["command"]
        == f"terraform init -backend-config=/project/./config/backend.tfvars"
    )


def test_init_with_args(terraform_container):
    """
    Test tf init with arguments.
    """
    with patch("dockerpty.exec_command") as mocked_pty:
        _init(["-migrate-state"])

    assert (
        mocked_pty.call_args_list[0].kwargs["command"]
        == f"terraform init -migrate-state -backend-config=/project/./config/backend.tfvars"
    )
