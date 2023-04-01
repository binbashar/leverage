from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.exceptions import Exit

from leverage.container import TerraformContainer
from leverage.containers.kubectl import KubeCtlContainer
from leverage.logger import _configure_logger, _leverage_logger

FAKE_ENV = {"TERRAFORM_IMAGE_TAG": "test", "PROJECT": "test"}
FAKE_HOST_CONFIG = {
    "NetworkMode": "default",
    "SecurityOpt": ["label:disable"],
    "Mounts": [],
}
AWS_EKS_UPDATE_KUBECONFIG = "aws eks update-kubeconfig --name test-cluster --profile test-profile --region us-east-1"


@pytest.fixture
def kubectl_container(muted_click_context):
    mocked_client = MagicMock()
    mocked_client.api.create_host_config.return_value = FAKE_HOST_CONFIG
    with patch("leverage.container.load_env", return_value=FAKE_ENV):
        container = KubeCtlContainer(mocked_client)
        container._run = Mock()
        return container


##############
# test utils #
##############


def test_get_eks_kube_config(kubectl_container):
    tf_output = "\r\naws eks update-kubeconfig --name test-cluster --profile test-profile\r\n"
    with patch.object(kubectl_container, "_start_with_output", return_value=(0, tf_output)):
        kubectl_container.common_conf["region_primary"] = "us-east-1"
        cmd = kubectl_container._get_eks_kube_config()

    assert cmd == AWS_EKS_UPDATE_KUBECONFIG


def test_get_eks_kube_config_tf_output_error(kubectl_container):
    """
    Test that if the TF OUTPUT fails, we get an error back.
    """
    with patch.object(kubectl_container, "_start_with_output", return_value=(1, "ERROR!")):
        with pytest.raises(Exit):
            kubectl_container._get_eks_kube_config()


@patch("os.getuid", Mock(return_value=1234))
def test_change_kube_file_owner_cmd(kubectl_container):
    with patch.object(kubectl_container, "_get_user_group_id", return_value=5678):
        assert kubectl_container._change_kube_file_owner_cmd() == "chown 1234:5678 /root/.kube/config"


def test_check_for_layer_location(kubectl_container, caplog):
    """
    Test that if we are not on a cluster layer, we raise an error.
    """
    _configure_logger(logger=_leverage_logger)
    _leverage_logger.propagate = True

    with patch.object(TerraformContainer, "check_for_layer_location"):  # assume parent method is already tested
        with pytest.raises(Exit):
            kubectl_container.cwd = Path("/random")
            kubectl_container.check_for_layer_location()

    assert caplog.messages[0] == "This command can only run at the [bold]cluster layer[/bold]."


#################
# test commands #
#################


def test_start_shell(kubectl_container):
    """
    Since this is a shell, we can only test with which parameters the container is spawned.
    It must have aws credentials and the .kube config folder sets properly.
    """
    kubectl_container.start_shell()
    container_args = kubectl_container.client.api.create_container.call_args[1]

    # we want a shell, so -> /bin/bash with no entrypoint
    assert container_args["command"] == "/bin/sh"
    assert container_args["entrypoint"] == ""

    # make sure we are pointing to the AWS credentials
    assert container_args["environment"]["AWS_CONFIG_FILE"] == "/root/tmp/test/config"
    assert container_args["environment"]["AWS_SHARED_CREDENTIALS_FILE"] == "/root/tmp/test/credentials"

    # make sure we mounted the .kube config folder
    assert next(m for m in container_args["host_config"]["Mounts"] if m["Target"] == "/root/.kube")

    # and the aws config folder
    assert next(m for m in container_args["host_config"]["Mounts"] if m["Target"] == "/root/tmp/test")


# don't rely on the OS user
@patch("os.getuid", Mock(return_value=1234))
@patch.object(KubeCtlContainer, "_get_user_group_id", Mock(return_value=5678))
# nor the filesystem
@patch.object(KubeCtlContainer, "check_for_layer_location", Mock())
# nor terraform
@patch.object(KubeCtlContainer, "_get_eks_kube_config", Mock(return_value=AWS_EKS_UPDATE_KUBECONFIG))
def test_configure(kubectl_container, caplog):
    with patch.object(kubectl_container, "_start", return_value=0) as mock_start:
        kubectl_container.configure()

    assert mock_start.call_args[0][0] == f'bash -c "{AWS_EKS_UPDATE_KUBECONFIG} && chown 1234:5678 /root/.kube/config"'
