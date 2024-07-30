from unittest import mock

import pytest

from leverage._utils import ExitError
from leverage.container import LeverageContainer
from tests.test_containers import container_fixture_factory


@pytest.fixture
def leverage_container(muted_click_context):
    return container_fixture_factory(LeverageContainer)


def test_mounts(muted_click_context):
    container = container_fixture_factory(
        LeverageContainer, mounts=(("/usr/bin", "/usr/bin"), ("/tmp/file.txt", "/tmp/file.txt"))
    )

    assert container.client.api.create_host_config.call_args_list[0][1]["mounts"] == [
        {"Target": "/usr/bin", "Source": "/usr/bin", "Type": "bind", "ReadOnly": False},
        {"Target": "/tmp/file.txt", "Source": "/tmp/file.txt", "Type": "bind", "ReadOnly": False},
    ]


def test_env_vars(muted_click_context):
    container = container_fixture_factory(LeverageContainer, env_vars={"testing": 123, "foo": "bar"})
    container.start(container.SHELL)

    container_args = container.client.api.create_container.call_args_list[0][1]
    assert container_args["environment"] == {"foo": "bar", "testing": 123}


def test_ensure_image_already_available(leverage_container: LeverageContainer, fake_os_user, propagate_logs, caplog):
    """
    Test that the local image is not re-built when is already available locally.
    """
    # already available
    with mock.patch.object(leverage_container.client.api, "images", return_value=True) as mocked_images:
        leverage_container.ensure_image()

    assert mocked_images.call_args_list[0][0][0] == "binbash/leverage-toolbox:test-5678-1234"
    assert caplog.messages[0] == "Checking for local docker image, tag: test-5678-1234..."
    assert "OK" in caplog.messages[1]


def test_ensure_image_failed(leverage_container: LeverageContainer, fake_os_user, propagate_logs, caplog):
    """
    Test that we get a friendly error if re-building the image fails.
    """
    build_response = [{"errorDetail": "Something went wrong"}]
    # not available
    with mock.patch.object(leverage_container.client.api, "images", return_value=False):
        with mock.patch.object(leverage_container.client.api, "build", return_value=build_response) as mocked_build:
            with pytest.raises(ExitError, match="Failed"):
                leverage_container.ensure_image()

    assert caplog.messages[1] == "Image not found, building it..."
    assert caplog.messages[2] == "Failed building local image: Something went wrong"


def test_ensure_image(leverage_container: LeverageContainer, fake_os_user, propagate_logs, caplog):
    """
    Test that the local image is not available locally, thus it has to be re-built.
    """
    build_response = [{"stream": "Successfully built"}]
    # not available
    with mock.patch.object(leverage_container.client.api, "images", return_value=False):
        with mock.patch.object(leverage_container.client.api, "build", return_value=build_response) as mocked_build:
            leverage_container.ensure_image()

    assert mocked_build.call_args_list[0][1]["buildargs"] == {
        "GID": "5678",
        "UID": "1234",
        "UNAME": "leverage",
        "IMAGE_TAG": "test",
    }
    assert caplog.messages[1] == "Image not found, building it..."
    assert "OK" in caplog.messages[2]
