from unittest.mock import patch, Mock

import pytest
from click import get_current_context
from click.exceptions import Exit

from leverage._internals import State
from leverage._utils import AwsCredsContainer, ExitError
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
    with patch.object(TerraformContainer, "check_for_layer_location", Mock()):
        # assume we have valid credentials
        with patch.object(AwsCredsContainer, "__enter__", Mock()):
            yield tf_container


def test_init(terraform_container):
    """
    Test happy path.
    """
    live_container = Mock()
    live_container.exec_run = Mock(return_value=(0, b"testing"))
    with patch("leverage._utils.LiveContainer.__enter__", return_value=live_container):
        _init([])

    assert live_container.exec_run.call_args_list[0].args[0] == "mkdir -p /root/.ssh"
    assert live_container.exec_run.call_args_list[1].args[0] == "chown root:root -R /root/.ssh/"
    assert (
        live_container.exec_run.call_args_list[2].args[0]
        == f"terraform init -backend-config=/project/./config/backend.tfvars"
    )


def test_init_with_args(terraform_container):
    """
    Test tf init with arguments.
    """
    live_container = Mock()
    live_container.exec_run = Mock(return_value=(0, b"testing"))
    with patch("leverage._utils.LiveContainer.__enter__", return_value=live_container):
        _init(["-migrate-state"])

    assert (
        live_container.exec_run.call_args_list[2].args[0]
        == f"terraform init -migrate-state -backend-config=/project/./config/backend.tfvars"
    )


def test_host_key_verification_failed(terraform_container):
    """
    Test missing public key on known_hosts file.
    """
    live_container = Mock()
    live_container.exec_run = Mock(return_value=(0, b"Host key verification failed"))
    with patch("leverage._utils.LiveContainer.__enter__", return_value=live_container):
        with pytest.raises(ExitError, match="You should add the missing public keys"):
            _init([])


def test_failed(terraform_container, caplog):
    """
    Test a failure from the tf init command.
    """
    live_container = Mock()
    live_container.exec_run = Mock(return_value=(1, b"Some random tf init failure"))
    with patch("leverage._utils.LiveContainer.__enter__", return_value=live_container):
        with pytest.raises(Exit):
            _init([])

    assert caplog.messages[0] == "Some random tf init failure"


def test_timeout(terraform_container, caplog):
    """
    Test a timeout error from the tf init command.
    """

    def side_effect(arg1: str, *args, **kwargs):
        if arg1.startswith("terraform init"):
            # we only want to raise the error on the init call
            raise TimeoutError("timed out")

    live_container = Mock()
    live_container.exec_run = Mock(side_effect=side_effect)
    with patch("leverage._utils.LiveContainer.__enter__", return_value=live_container):
        with pytest.raises(ExitError, match="timed out"):
            _init([])
