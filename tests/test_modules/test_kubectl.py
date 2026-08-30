from importlib import import_module
from pathlib import Path, PosixPath
from unittest import mock
from unittest.mock import Mock, patch

from click.testing import CliRunner

from leverage import leverage
from leverage.modules.kubectl import _scan_clusters, ClusterInfo

# `leverage.modules.kubectl` resolves to the click Group of the same name, since it is
# re-exported in `leverage/modules/__init__.py`. Patching by string would target that Group
# instead of the module, so the module itself is imported and patched by object.
kubectl_module = import_module("leverage.modules.kubectl")


def test_scan_clusters():
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

                first_found = next(_scan_clusters(Path.cwd()))

    # compare
    assert first_found[0] == PosixPath("/foo/bar/")
    assert first_found[1]["type"] == "k8s-eks-cluster"


def test_discover(leverage_project):
    """
    Test that, given a layer with a valid cluster file, we are able to call the k8s configuration routine.
    """
    mocked_cluster_data = {
        "type": "k8s-eks-cluster",
        "data": {"cluster_name": "test", "profile": "test", "region": "us-east-1"},
    }
    cli_runner = CliRunner()
    with cli_runner.isolated_filesystem(leverage_project) as leverage_project_folder:
        # The command only reaches _configure, so the binary does not need to be installed here.
        # Runner binary discovery is covered on its own in tests/test_modules/test_runner.py.
        with patch.object(kubectl_module.Runner, "_validate_binary", lambda runner: None), patch.object(
            kubectl_module, "_scan_clusters", return_value=[(leverage_project_folder, mocked_cluster_data)]
        ) as mkd_scan_clusters:
            with patch("simple_term_menu.TerminalMenu") as mkd_show:
                mkd_show.return_value.show.return_value = 0  # simulate choosing the first result
                with patch.object(kubectl_module, "_configure") as mkd_configure:
                    cli_runner.invoke(leverage, ["kubectl", "discover"])

    assert isinstance(mkd_configure.call_args_list[0][0][1], ClusterInfo)
