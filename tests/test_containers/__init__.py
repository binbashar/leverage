from unittest.mock import MagicMock, patch, Mock

FAKE_ENV = {"TERRAFORM_IMAGE_TAG": "test", "PROJECT": "test"}

FAKE_HOST_CONFIG = {
    "NetworkMode": "default",
    "SecurityOpt": ["label:disable"],
    "Mounts": [],
}
