from unittest.mock import MagicMock, Mock, patch

from leverage.container import TerraformContainer

FAKE_ENV = {"TERRAFORM_IMAGE_TAG": "test", "PROJECT": "test"}
FAKE_HOST_CONFIG = {
    "NetworkMode": "default",
    "SecurityOpt": ["label:disable"],
    "Mounts": [],
}


@patch("os.getenv", Mock(return_value="/home/testing/.terraform/cache"))
def test_tf_plugin_cache_dir(muted_click_context):
    """
    Given `TF_PLUGIN_CACHE_DIR` is set as an env var on the host
    we expect it to be on the container too, and also as a mounted folder.
    """
    mocked_client = MagicMock()
    mocked_client.api.create_host_config.return_value = FAKE_HOST_CONFIG
    with patch("leverage.container.load_env", return_value=FAKE_ENV):
        container = TerraformContainer(mocked_client)
        container._run = Mock()

    # call any command to trigger a container creation
    container.start_shell()
    container_args = container.client.api.create_container.call_args[1]

    # make sure the env var is on place
    assert container_args["environment"]["TF_PLUGIN_CACHE_DIR"] == "/home/testing/.terraform/cache"

    # and the cache folder mounted
    assert next(m for m in container_args["host_config"]["Mounts"] if m["Target"] == "/home/testing/.terraform/cache")
