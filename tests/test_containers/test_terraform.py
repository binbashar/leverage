from unittest import mock

import pytest

from leverage.container import TFContainer
from tests.test_containers import container_fixture_factory


@pytest.fixture
def tf_container(muted_click_context, monkeypatch):
    monkeypatch.setenv("TF_PLUGIN_CACHE_DIR", "/home/testing/.terraform/cache")
    return container_fixture_factory(TFContainer)


def test_tf_plugin_cache_dir(tf_container):
    """
    Given `TF_PLUGIN_CACHE_DIR` is set as an env var on the host
    we expect it to be on the container too, and also as a mounted folder.
    """
    # call any command to trigger a container creation
    tf_container.start_shell()
    container_args = tf_container.client.api.create_container.call_args[1]

    # make sure the env var is on place
    assert container_args["environment"]["TF_PLUGIN_CACHE_DIR"] == "/home/testing/.terraform/cache"

    # and the cache folder mounted
    assert next(m for m in container_args["host_config"]["Mounts"] if m["Target"] == "/home/testing/.terraform/cache")


@mock.patch("leverage.container.refresh_layer_credentials")
def test_refresh_credentials(mock_refresh, tf_container):
    tf_container.enable_sso()
    tf_container.refresh_credentials()
    container_args = tf_container.client.api.create_container.call_args_list[0][1]

    # we want a shell, so -> /bin/bash and refresh_sso_credentials flag
    assert container_args["command"] == 'echo "Done."'
    assert mock_refresh.assert_called_once


@mock.patch("leverage.container.refresh_layer_credentials")
def test_auth_method_sso_enabled(mock_refresh, tf_container):
    tf_container.sso_enabled = True
    tf_container.auth_method()

    assert mock_refresh.assert_called_once


def test_auth_method_mfa_enabled(tf_container):
    tf_container.sso_enabled = False
    tf_container.mfa_enabled = True

    assert tf_container.auth_method() == "/home/leverage/scripts/aws-mfa/aws-mfa-entrypoint.sh -- "


def test_auth_method_else(tf_container):
    tf_container.sso_enabled = False
    tf_container.mfa_enabled = False

    assert tf_container.auth_method() == ""
