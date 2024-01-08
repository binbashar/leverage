from unittest.mock import Mock, MagicMock

from leverage.modules.aws import get_account_roles, add_sso_profile, configure_sso_profiles


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

    assert get_account_roles(sso_client, "token-123") == {
        "accName1": {
            "account_id": "accId1",
            "role_name": "devops",
        },
        "accName2": {
            "account_id": "accId2",
            "role_name": "devops",
        },
    }


def test_add_sso_profile():
    mocked_section = MagicMock()
    add_sso_profile(mocked_section, "section_1", "role_1", "acc_id_1", "us-east-1", "https://test.awsapps.com/start")

    assert mocked_section.get_section.mock_calls[1].args == ("role_name", "role_1")
    assert mocked_section.get_section.mock_calls[2].args == ("account_id", "acc_id_1")
    assert mocked_section.get_section.mock_calls[3].args == ("sso_region", "us-east-1")
    assert mocked_section.get_section.mock_calls[4].args == ("sso_start_url", "https://test.awsapps.com/start")


def test_configure_sso_profiles():
    pass
