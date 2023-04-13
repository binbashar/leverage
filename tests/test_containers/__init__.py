from unittest.mock import MagicMock, patch, Mock

FAKE_ENV = {"TERRAFORM_IMAGE_TAG": "test", "PROJECT": "test"}

FAKE_HOST_CONFIG = {
    "NetworkMode": "default",
    "SecurityOpt": ["label:disable"],
    "Mounts": [],
}


def container_fixture_factory(container_class):
    """
    Given a container class, return an instance of it with patched working variables.
    """
    mocked_client = MagicMock()
    mocked_client.api.create_host_config.return_value = FAKE_HOST_CONFIG
    with patch("leverage.container.load_env", return_value=FAKE_ENV):
        container = container_class(mocked_client)
        container._run = Mock()
        return container
