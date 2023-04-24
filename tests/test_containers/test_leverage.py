from unittest.mock import patch, Mock

import pytest

from leverage.container import LeverageContainer
from tests.test_containers import container_fixture_factory


@pytest.fixture
def leverage_container(muted_click_context):
    return container_fixture_factory(LeverageContainer)


@patch("pwd.getpwuid")
def test_get_current_user_group_id(mocked_get_pw, leverage_container):
    mocked_get_pw.return_value = Mock(pw_gid=5678)
    assert leverage_container.get_current_user_group_id(1000) == 5678


def test_change_ownership_cmd(leverage_container, fake_os_user):
    assert leverage_container.change_ownership_cmd("/tmp/") == "chown 1234:5678 -R /tmp/"


def test_change_ownership_non_recursive_cmd(leverage_container, fake_os_user):
    assert leverage_container.change_ownership_cmd("/tmp/file.txt", recursive=False) == "chown 1234:5678 /tmp/file.txt"
