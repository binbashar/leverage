import pytest

from leverage.container import TerraformContainer
from tests.test_containers import container_fixture_factory


@pytest.fixture
def terraform_container(muted_click_context, monkeypatch):
    monkeypatch.setenv("TF_PLUGIN_CACHE_DIR", "/home/testing/.terraform/cache")
    return container_fixture_factory(TerraformContainer)


def test_tf_plugin_cache_dir(terraform_container):
    """
    Given `TF_PLUGIN_CACHE_DIR` is set as an env var on the host
    we expect it to be on the container too, and also as a mounted folder.
    """
    # call any command to trigger a container creation
    terraform_container.start_shell()
    container_args = terraform_container.client.api.create_container.call_args[1]

    # make sure the env var is on place
    assert container_args["environment"]["TF_PLUGIN_CACHE_DIR"] == "/home/testing/.terraform/cache"

    # and the cache folder mounted
    assert next(m for m in container_args["host_config"]["Mounts"] if m["Target"] == "/home/testing/.terraform/cache")


def test_refresh_credentials(terraform_container):
    terraform_container.enable_sso()
    terraform_container.refresh_credentials()
    container_args = terraform_container.client.api.create_container.call_args_list[0][1]

    # we want a shell, so -> /bin/bash and refresh_sso_credentials flag
    assert container_args["command"] == 'echo "Done."'
    assert terraform_container.refresh_sso_credentials
