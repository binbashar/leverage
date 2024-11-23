from pathlib import Path, PosixPath
from unittest import mock
from unittest.mock import Mock, patch

import pytest
from click.exceptions import Exit

from leverage.containers.kubectl import KubeCtlContainer, ClusterInfo
from leverage.path import PathsHandler
from tests.test_containers import container_fixture_factory

AWS_EKS_UPDATE_KUBECONFIG = "aws eks update-kubeconfig --name test-cluster --profile test-profile --region us-east-1"


@pytest.fixture
def kubectl_container(muted_click_context):
    return container_fixture_factory(KubeCtlContainer)


##############
# test utils #
##############


def test_get_eks_kube_config(kubectl_container):
    tf_output = "\r\naws eks update-kubeconfig --name test-cluster --profile test-profile\r\n"
    with patch.object(kubectl_container, "_start_with_output", return_value=(0, tf_output)):
        kubectl_container.paths.cwd = Path("/project/account/us-east-1/cluster")
        cmd = kubectl_container._get_eks_kube_config()

    assert cmd == AWS_EKS_UPDATE_KUBECONFIG


def test_get_eks_kube_config_tf_output_error(kubectl_container):
    """
    Test that if the TF OUTPUT fails, we get an error back.
    """
    with patch.object(kubectl_container, "_start_with_output", return_value=(1, "ERROR!")):
        with pytest.raises(Exit):
            kubectl_container._get_eks_kube_config()


#################
# test commands #
#################


def test_start_shell(kubectl_container):
    """
    Since this is a shell, we can only test with which parameters the container is spawned.
    It must have aws credentials and the .kube config folder sets properly.
    """
    kubectl_container.start_shell()
    container_args = kubectl_container.client.api.create_container.call_args_list[0][1]

    # we want a shell, so -> /bin/bash with no entrypoint
    assert container_args["command"] == "/bin/bash"
    assert container_args["entrypoint"] == ""

    # make sure we are pointing to the AWS credentials
    assert container_args["environment"]["AWS_CONFIG_FILE"] == "/home/leverage/tmp/test/config"
    assert container_args["environment"]["AWS_SHARED_CREDENTIALS_FILE"] == "/home/leverage/tmp/test/credentials"

    # make sure we mounted the .kube config folder
    print(container_args["host_config"])
    assert next(m for m in container_args["host_config"]["Mounts"] if m["Target"] == "/home/leverage/.kube")

    # and the aws config folder
    assert next(m for m in container_args["host_config"]["Mounts"] if m["Target"] == "/home/leverage/tmp/test")


# don't rely on the filesystem
@patch.object(PathsHandler, "check_for_cluster_layer", Mock())
# nor terraform
@patch.object(KubeCtlContainer, "_get_eks_kube_config", Mock(return_value=AWS_EKS_UPDATE_KUBECONFIG))
def test_configure(kubectl_container, fake_os_user):
    with patch.object(kubectl_container, "_start", return_value=0) as mock_start:
        kubectl_container.configure()

    assert mock_start.call_args[0][0] == AWS_EKS_UPDATE_KUBECONFIG


#####################
# test auth methods #
#####################


def test_start_shell_mfa(kubectl_container):
    """
    Make sure the command is executed through the proper MFA script.
    """
    kubectl_container.enable_mfa()
    # mock the __exit__ of the context manager to avoid the restoration of the values
    # otherwise the asserts around /.aws/ wouldn't be possible
    with patch("leverage._utils.AwsCredsEntryPoint.__exit__"):
        kubectl_container.start_shell()
        container_args = kubectl_container.client.api.create_container.call_args_list[0][1]

    # we want a shell, so -> /bin/bash with no entrypoint
    assert container_args["command"] == "/bin/bash"
    assert container_args["entrypoint"] == "/home/leverage/scripts/aws-mfa/aws-mfa-entrypoint.sh -- "

    # make sure we are pointing to the right AWS credentials: /.aws/ folder for MFA
    assert container_args["environment"]["AWS_CONFIG_FILE"] == "/home/leverage/.aws/test/config"
    assert container_args["environment"]["AWS_SHARED_CREDENTIALS_FILE"] == "/home/leverage/.aws/test/credentials"


@patch("leverage.container.refresh_layer_credentials")
def test_start_shell_sso(mock_refresh, kubectl_container):
    """
    Make sure the SSO flag is set properly before the command.
    """
    kubectl_container.enable_sso()
    kubectl_container._check_sso_token = Mock(return_value=True)
    kubectl_container.start_shell()
    container_args = kubectl_container.client.api.create_container.call_args_list[0][1]

    # we want a shell, so -> /bin/bash and refresh_sso_credentials flag
    assert container_args["command"] == "/bin/bash"
    assert mock_refresh.assert_called_once

    # make sure we are pointing to the right AWS credentials: /tmp/ folder for SSO
    assert container_args["environment"]["AWS_CONFIG_FILE"] == "/home/leverage/tmp/test/config"
    assert container_args["environment"]["AWS_SHARED_CREDENTIALS_FILE"] == "/home/leverage/tmp/test/credentials"


def test_scan_clusters(kubectl_container: KubeCtlContainer):
    """
    Test that we can find valid metadata.yaml presents in the down the path of the filesystem tree where we are staying.
    """
    # mock and call
    with mock.patch("os.walk") as mock_walk:
        with patch("builtins.open"):
            with mock.patch("ruamel.yaml.safe_load") as mock_yaml:
                mock_walk.return_value = [
                    ("/foo", ["bar"], ("baz",)),
                    ("/foo/bar", [], ("spam", "metadata.yaml")),
                ]
                mock_yaml.return_value = {"type": "k8s-eks-cluster"}

                first_found = next(kubectl_container._scan_clusters())

    # compare
    assert first_found[0] == PosixPath("/foo/bar/")
    assert first_found[1]["type"] == "k8s-eks-cluster"


def test_discover(kubectl_container: KubeCtlContainer):
    """
    Test that, given a layer with a valid cluster file, we are able to call the k8s configuration routine.
    """
    mocked_cluster_data = {
        "type": "k8s-eks-cluster",
        "data": {"cluster_name": "test", "profile": "test", "region": "us-east-1"},
    }
    with patch.object(kubectl_container, "_scan_clusters", return_value=[(Path.cwd(), mocked_cluster_data)]):
        with patch("simple_term_menu.TerminalMenu") as mkd_show:
            mkd_show.return_value.show.return_value = 0  # simulate choosing the first result
            with patch.object(kubectl_container.paths, "update_cwd") as mkd_update:
                with patch.object(kubectl_container, "configure") as mkd_configure:
                    kubectl_container.discover()

    assert mkd_update.called
    assert isinstance(mkd_configure.call_args_list[0][0][0], ClusterInfo)
