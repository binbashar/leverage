from unittest import mock
from unittest.mock import Mock

import pytest

from leverage._utils import ExitError
from leverage.modules.credentials import _load_configs_for_credentials, configure_accounts_profiles


@mock.patch(
    "leverage.modules.credentials._load_project_yaml",
    Mock(
        return_value={
            "short_name": "test",
            "region": "us-test-1",
            "organization": {
                "accounts": [
                    {"name": "acc2"},
                ]
            },
        }
    ),
)
@mock.patch(
    "leverage.modules.credentials.AWSCLI",
    Mock(
        env_conf={
            "PROJECT": "test",
            "MFA_ENABLED": "true",
        },
        paths=Mock(
            common_conf={
                "project_long": "test-prjt",
                "region_secondary": "us-test-2",
                "accounts": {
                    "acc1": {
                        "email": "test@test.com",
                        "id": "123456",
                    }
                },
            },
        ),
    ),
)
def test_load_configs_for_credentials(with_click_context):
    assert _load_configs_for_credentials() == {
        "mfa_enabled": "true",
        "organization": {
            "accounts": [
                {
                    "email": "test@test.com",
                    "id": "123456",
                    "name": "acc1",
                },
                {
                    "name": "acc2",
                },
            ]
        },
        "primary_region": "us-test-1",
        "project_name": "test-prjt",
        "secondary_region": "us-test-2",
        "short_name": "test",
    }


@pytest.mark.parametrize("mfa_device", [False, True])
@mock.patch("leverage.modules.credentials._get_mfa_serial", new=Mock(return_value="mfa123"))
@mock.patch("leverage.modules.credentials._backup_file")
def test_configure_accounts_profiles(mocked_backup, mfa_device, muted_click_context):
    """
    Test that the expected jsons for the aws credentials are generated as expected.
    Cover both mfa and no-mfa cases.
    """
    with mock.patch("leverage.modules.credentials.configure_profile") as mocked_config:
        configure_accounts_profiles(
            "test-management",
            "us-test-1",
            {"acc1": "12345", "out-of-project-acc": "67890"},
            [{"name": "acc1"}],
            mfa_device,
        )

    # make sure we did a backup with the old credentials
    assert mocked_backup.called_once

    # only 1 call since "out-of-project-acc" should be avoided
    assert mocked_config.call_count == 1
    assert mocked_config.call_args_list[0][0][0] == "test-acc1-oaar"
    expected = {
        "output": "json",
        "region": "us-test-1",
        "role_arn": f"arn:aws:iam::12345:role/OrganizationAccountAccessRole",
        "source_profile": "test-management",
    }
    if mfa_device:
        expected["mfa_serial"] = "mfa123"

    assert mocked_config.call_args_list[0][0][1] == expected


@mock.patch("leverage.modules.credentials._get_mfa_serial", new=Mock(return_value=""))
def test_configure_accounts_profiles_mfa_error(muted_click_context):
    """
    Test that if we fail to fetch the MFA serial number, user get a proper error.
    """
    with pytest.raises(ExitError, match="No MFA device found for user."):
        configure_accounts_profiles("test-management", "us-test-1", {}, [], True)
