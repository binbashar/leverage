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
    _credentials_are_valid,
    _get_management_account_id,
    configure_profile,
    _update_account_ids,
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


@mock.patch("leverage.modules.credentials._get_mfa_serial", new=Mock(return_value="mfa123"))
@mock.patch("leverage.modules.credentials._backup_file")
def test_configure_accounts_profiles(mocked_backup, muted_click_context):
    """
    Test that the expected jsons for the aws credentials are generated as expected.
    No-mfa case.
    """
    with mock.patch("leverage.modules.credentials.configure_profile") as mocked_config:
        configure_accounts_profiles(
            "test-management",
            "us-test-1",
            {"acc1": "12345", "out-of-project-acc": "67890"},
            [{"name": "acc1"}],
            fetch_mfa_device=False,
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

    assert mocked_config.call_args_list[0][0][1] == expected


@pytest.mark.parametrize("mfa_device", [False, True])
@mock.patch("leverage.modules.credentials._get_mfa_serial", new=Mock(return_value="mfa123"))
@mock.patch("leverage.modules.credentials._backup_file")
def test_configure_accounts_profiles_mfa(mocked_backup, mfa_device, muted_click_context):
    """
    Test that the expected jsons for the aws credentials are generated as expected.
    Mfa case.
    """
    with mock.patch("leverage.modules.credentials.configure_profile") as mocked_config:
        configure_accounts_profiles(
            "test-management",
            "us-test-1",
            {"acc1": "12345", "out-of-project-acc": "67890"},
            [{"name": "acc1"}],
            fetch_mfa_device=True,
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
        "mfa_serial": "mfa123",
    }

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
    """
    Test that the access and secret keys are extracted and validated correctly
    from the credentials.csv file provided by AWS.
    """
    assert _extract_credentials(Path("credentials.csv")) == (
        "ACCESSKEYXXXXXXXXXXX",
        "secretkeyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    )


def test_get_organization_accounts():
    """
    Test that the list of accounts of an organization are queried and returned in a {acc name:  acc id} dict.
    """
    mocked_aws_cli.exec = Mock(return_value=(0, '{"Accounts": [{"Name": "test-acc1", "Id": "12345"}]}'))
    with mock.patch("leverage.modules.credentials.AWSCLI", mocked_aws_cli):
        assert _get_organization_accounts("foo", "bar") == {"test-acc1": "12345"}


def test_get_organization_accounts_error():
    """
    Test that, if getting the list of accounts fails for some reason, we return an empty dict.
    """
    mocked_aws_cli.exec = Mock(return_value=(1, "BAD"))
    with mock.patch("leverage.modules.credentials.AWSCLI", mocked_aws_cli):
        assert _get_organization_accounts("foo", "bar") == {}


def test_get_mfa_serial():
    """
    Test that we fetch the mfa devices from the profile and return the serial number of the first one that is valid.
    """
    mocked_aws_cli.exec = Mock(
        return_value=(0, '{"MFADevices": [{"SerialNumber": "arn:aws:iam::123456789012:mfa/testuser"}]}')
    )
    with mock.patch("leverage.modules.credentials.AWSCLI", mocked_aws_cli):
        assert _get_mfa_serial("foo") == "arn:aws:iam::123456789012:mfa/testuser"


def test_get_mfa_serial_error(muted_click_context):
    """
    Test that, if fetching mfa devices fails, we return a user-friendly error.
    """
    mocked_aws_cli.exec = Mock(return_value=(1, "BAD"))
    with mock.patch("leverage.modules.credentials.AWSCLI", mocked_aws_cli):
        with pytest.raises(ExitError, match="AWS CLI error: BAD"):
            _get_mfa_serial("foo")


def test_credentials_are_valid():
    """
    Test that AWS credentials for the current profile are valid.
    """
    mocked_aws_cli.exec = Mock(return_value=(0, "OK"))
    with mock.patch("leverage.modules.credentials.AWSCLI", mocked_aws_cli):
        assert _credentials_are_valid("foo")


def test_get_management_account_id():
    """
    Test that we can get the account id from the current profile.
    """
    mocked_aws_cli.exec = Mock(return_value=(0, '{"Account": "123456789012"}'))
    with mock.patch("leverage.modules.credentials.AWSCLI", mocked_aws_cli):
        assert _get_management_account_id("foo") == "123456789012"


def test_get_management_account_id_error(with_click_context):
    """
    Test that we return a user-friendly error if getting the account id of a profile fails.
    """
    mocked_aws_cli.exec = Mock(return_value=(1, "BAD"))
    with mock.patch("leverage.modules.credentials.AWSCLI", mocked_aws_cli):
        with pytest.raises(ExitError, match="AWS CLI error: BAD"):
            _get_management_account_id("foo")


def test_configure_credentials(with_click_context, propagate_logs, caplog):
    """
    Test that the aws credentials for the profile are set and the backup feature is called.
    """
    mocked_aws_cli.exec = Mock(return_value=(0, ""))
    with mock.patch("leverage.modules.credentials._backup_file"):
        with mock.patch("leverage.modules.credentials._ask_for_credentials", new=Mock(return_value=("foo", "bar"))):
            with mock.patch("leverage.modules.credentials.AWSCLI", mocked_aws_cli):
                configure_credentials("foo", "manual", make_backup=True)

    assert caplog.messages[0] == "Backing up credentials file."


def test_configure_credentials_error(with_click_context):
    """
    Test that, if settings the credentials for a profile fails, we return a user-friendly error.
    """
    mocked_aws_cli.exec = Mock(return_value=(1, "BROKEN"))
    with mock.patch("leverage.modules.credentials._extract_credentials", new=Mock(return_value=("foo", "bar"))):
        with mock.patch("leverage.modules.credentials.AWSCLI", mocked_aws_cli):
            with pytest.raises(ExitError, match="AWS CLI error: BROKEN"):
                configure_credentials("foo", "/.aws/creds")


def test_update_account_ids(with_click_context, propagate_logs):
    """
    Test that account ids are updated in global configuration files.
    """
    mocked_aws_cli.system_exec = Mock()
    with mock.patch("leverage.modules.credentials.PROJECT_COMMON_TFVARS"):
        with mock.patch("leverage.modules.credentials.AWSCLI", mocked_aws_cli):
            _update_account_ids(
                {
                    "project_name": "test",
                    "organization": {
                        "accounts": [
                            {
                                "name": "acc1",
                                "email": "acc@test.com",
                                "id": "12345",
                            }
                        ]
                    },
                }
            )

    assert (
        mocked_aws_cli.system_exec.call_args_list[0][0][0]
        == 'hcledit -f /test/config/common.tfvars -u attribute set acc1_account_id "\\"12345\\""'
    )

    assert (
        mocked_aws_cli.system_exec.call_args_list[1][0][0]
        == """hcledit -f /test/config/common.tfvars -u attribute set accounts '{
  acc1 = {
    email = \"acc@test.com\",
    id = \"12345\"
  }
}'"""
    )
