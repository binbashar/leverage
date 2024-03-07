from pathlib import Path
from unittest import mock
from unittest.mock import Mock

import pytest

from leverage._utils import ExitError
from leverage.modules.credentials import (
    _load_configs_for_credentials,
    configure_accounts_profiles,
    _extract_credentials,
    _get_mfa_serial,
    _get_organization_accounts,
    _profile_is_configured,
    _backup_file,
    configure_credentials,
)

mocked_aws_cli = Mock()


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


@mock.patch(
    "builtins.open",
    new_callable=mock.mock_open,
    read_data="""Access key ID,Secret access key
ACCESSKEYXXXXXXXXXXX,secretkeyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
""",
)
def test_extract_credentials(mocked_open):
    assert _extract_credentials(Path("credentials.csv")) == (
        "ACCESSKEYXXXXXXXXXXX",
        "secretkeyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    )


def test_get_organization_accounts():
    mocked_aws_cli.exec = Mock(return_value=(0, '{"Accounts": [{"Name": "test-acc1", "Id": "12345"}]}'))
    with mock.patch("leverage.modules.credentials.AWSCLI", mocked_aws_cli):
        assert _get_organization_accounts("foo", "bar") == {"test-acc1": "12345"}


def test_get_organization_accounts_error():
    mocked_aws_cli.exec = Mock(return_value=(1, "BAD"))
    with mock.patch("leverage.modules.credentials.AWSCLI", mocked_aws_cli):
        assert _get_organization_accounts("foo", "bar") == {}


def test_get_mfa_serial():
    mocked_aws_cli.exec = Mock(
        return_value=(0, '{"MFADevices": [{"SerialNumber": "arn:aws:iam::123456789012:mfa/testuser"}]}')
    )
    with mock.patch("leverage.modules.credentials.AWSCLI", mocked_aws_cli):
        assert _get_mfa_serial("foo") == "arn:aws:iam::123456789012:mfa/testuser"


def test_get_mfa_serial_error(muted_click_context):
    mocked_aws_cli.exec = Mock(return_value=(1, "BAD"))
    with mock.patch("leverage.modules.credentials.AWSCLI", mocked_aws_cli):
        with pytest.raises(ExitError, match="AWS CLI error: BAD"):
            _get_mfa_serial("foo")


def test_profile_is_configured():
    mocked_aws_cli.exec = Mock(return_value=(0, "OK"))
    with mock.patch("leverage.modules.credentials.AWSCLI", mocked_aws_cli):
        assert _profile_is_configured("foo")


def test_backup_file():
    with mock.patch("leverage.modules.credentials.AWSCLI", mocked_aws_cli):
        _backup_file("config")

    assert (
        mocked_aws_cli.system_exec.call_args_list[0][0][0] == "sh -c 'cp $AWS_CONFIG_FILE \"${AWS_CONFIG_FILE}.bkp\"'"
    )


def test_configure_credentials(with_click_context, propagate_logs, caplog):
    mocked_aws_cli.exec = Mock(return_value=(0, ""))
    with mock.patch("leverage.modules.credentials._backup_file"):
        with mock.patch("leverage.modules.credentials._ask_for_credentials", new=Mock(return_value=("foo", "bar"))):
            with mock.patch("leverage.modules.credentials.AWSCLI", mocked_aws_cli):
                configure_credentials("foo", "manual", make_backup=True)

    assert caplog.messages[0] == "Backing up credentials file."


def test_configure_credentials_error(with_click_context):
    mocked_aws_cli.exec = Mock(return_value=(1, "BROKEN"))
    with mock.patch("leverage.modules.credentials._extract_credentials", new=Mock(return_value=("foo", "bar"))):
        with mock.patch("leverage.modules.credentials.AWSCLI", mocked_aws_cli):
            with pytest.raises(ExitError, match="AWS CLI error: BROKEN"):
                configure_credentials("foo", "/.aws/creds")
