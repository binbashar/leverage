import pytest

from leverage.container import LeverageContainer
from tests.test_containers import container_fixture_factory


@pytest.fixture
def leverage_container(muted_click_context):
    return container_fixture_factory(LeverageContainer)


def test_change_ownership_cmd(leverage_container, fake_os_user):
    assert leverage_container.change_ownership_cmd("/tmp/", recursive=True) == "chown 1234:5678 -R /tmp/"


def test_change_ownership_non_recursive_cmd(leverage_container, fake_os_user):
    assert leverage_container.change_ownership_cmd("/tmp/file.txt", recursive=False) == "chown 1234:5678 /tmp/file.txt"


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
