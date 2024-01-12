from collections import namedtuple
from unittest import mock
from unittest.mock import Mock, MagicMock

import pytest

from leverage.container import SSOContainer
from leverage.modules.aws import get_account_roles, add_sso_profile, configure_sso_profiles
from tests.test_containers import container_fixture_factory


@pytest.fixture
def sso_container(muted_click_context):
    mocked_cont = container_fixture_factory(SSOContainer)
    mocked_cont.get_sso_access_token = Mock(return_value="testing-token")

    return mocked_cont


ACC_ROLES = {
    "accName1": {
        "account_id": "accId1",
        "role_name": "devops",
    },
    "accName2": {
        "account_id": "accId2",
        "role_name": "devops",
    },
}


def test_get_account_roles():
    sso_client = Mock()
    sso_client.list_accounts = Mock(
        return_value={
            "accountList": [
                {
                    "accountId": "accId1",
                    "accountName": "accName1",
                },
                {
                    "accountId": "accId2",
                    "accountName": "accName2",
                },
            ]
        }
    )
    sso_client.list_account_roles = Mock(return_value={"roleList": [{"roleName": "devops"}]})

    assert get_account_roles(sso_client, "token-123") == ACC_ROLES


def test_add_sso_profile():
    mocked_section = MagicMock()
    add_sso_profile(mocked_section, "section_1", "role_1", "acc_id_1", "us-east-1", "https://test.awsapps.com/start")

    assert mocked_section.get_section.mock_calls[1].args == ("role_name", "role_1")
    assert mocked_section.get_section.mock_calls[2].args == ("account_id", "acc_id_1")
    assert mocked_section.get_section.mock_calls[3].args == ("sso_region", "us-east-1")
    assert mocked_section.get_section.mock_calls[4].args == ("sso_start_url", "https://test.awsapps.com/start")


UpdaterAttr = namedtuple("UpdaterAttr", ["value"])
mocked_updater = MagicMock()
mocked_updater.__getitem__.return_value = {
    "sso_region": UpdaterAttr(value="us-test-1"),
    "sso_start_url": UpdaterAttr(value="https://test.awsapps.com/start"),
}


@mock.patch("boto3.client")
def test_configure_sso_profiles(mocked_boto, sso_container):
    with mock.patch("leverage.modules.aws.ConfigUpdater.__new__", return_value=mocked_updater):
        with mock.patch("leverage.modules.aws.get_account_roles", return_value=ACC_ROLES):
            with mock.patch("leverage.modules.aws.add_sso_profile") as mocked_add_profile:
                configure_sso_profiles(sso_container)

    # 2 profiles were added
    assert mocked_add_profile.call_args_list[0].args[1:] == (
        "profile test-sso-accName1",
        "devops",
        "accId1",
        "us-test-1",
        "https://test.awsapps.com/start",
    )
    assert mocked_add_profile.call_args_list[1].args[1:] == (
        "profile test-sso-accName2",
        "devops",
        "accId2",
        "us-test-1",
        "https://test.awsapps.com/start",
    )
    # and the file was saved
    assert mocked_updater.update_file.called
