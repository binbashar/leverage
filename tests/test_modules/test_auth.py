from collections import namedtuple
from importlib import import_module
from pathlib import PosixPath
from unittest import mock
from unittest.mock import Mock, MagicMock

import pytest
from botocore.exceptions import ClientError
from configupdater import ConfigUpdater

from leverage import leverage
from leverage._utils import ExitError
from leverage.path import PathsHandler
from leverage.modules.auth import (
    refresh_layer_credentials,
    get_layer_profile,
    SkipProfile,
    refresh_all_accounts_credentials,
)
from leverage.modules.aws import get_account_roles, add_sso_profile, configure_sso_profiles

# `leverage.modules.aws` resolves to the click Group of the same name, since it is re-exported
# in `leverage/modules/__init__.py`. Patching by string would target that Group instead of the
# module, so the module itself is imported and patched by object.
aws_module = import_module("leverage.modules.aws")


@pytest.fixture
def paths(with_click_context, propagate_logs):
    """
    Mock PathsHandler used by auth.py functions.

    Backed by a MagicMock(spec=PathsHandler) so unexpected attribute access fails loudly. Path-like
    attributes are real PosixPath instances so the patched `pathlib.Path.read_text` and
    `configupdater.parser.open` side effects in the tests can resolve files via `data_dict`.
    """
    mocked = MagicMock(spec=PathsHandler)
    mocked.project = "test"
    mocked.project_long = "binbash-test"
    mocked.aws_config_file = PosixPath("~/.aws/test/config")
    mocked.aws_credentials_file = PosixPath("~/.aws/test/credentials")
    mocked.backend_tfvars = PosixPath("~/config/backend.tfvars")
    mocked.cwd = PosixPath("~/some/layer")
    mocked.sso_cache = PosixPath("~/.aws/test/sso/cache")
    mocked.sso_token_file = PosixPath("~/.aws/test/sso/cache/token")
    return mocked


@pytest.fixture
def mock_sso_token():
    """Mock get_sso_access_token() to return a fixed token without touching disk.

    Patches both bindings (auth.py defines it, aws.py imports it) so any caller in either
    module hits the same fake.
    """
    with mock.patch("leverage.modules.auth.get_sso_access_token", return_value="testing-token") as m, mock.patch.object(
        aws_module, "get_sso_access_token", return_value="testing-token"
    ):
        yield m


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
def test_configure_sso_profiles(mocked_boto, paths, mock_sso_token):
    with mock.patch.object(aws_module.ConfigUpdater, "__new__", return_value=mocked_updater):
        with mock.patch.object(aws_module, "get_account_roles", return_value=ACC_ROLES):
            with mock.patch.object(aws_module, "add_sso_profile") as mocked_add_profile:
                configure_sso_profiles(paths)

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


@pytest.mark.parametrize("profile", ["local.account.profile", "${local.profile}-test-devops"])
def test_get_layer_profile_skip_profile(profile):
    with pytest.raises(SkipProfile):
        get_layer_profile(profile, Mock(), "DevOps", "project")


def test_get_layer_profile_no_section_error(muted_click_context):
    updater = ConfigUpdater()  # empty config -> no sections
    with pytest.raises(ExitError, match="Missing project-sso-acc123 permission for account acc123."):
        get_layer_profile("project-acc123-devops", updater, "DevOps", "project")


def test_get_layer_profile(muted_click_context):
    updater = ConfigUpdater()
    updater_values = [
        UpdaterAttr(value="123"),  # first call: account
        UpdaterAttr(value="devops"),  # second call: role
    ]

    with mock.patch.object(updater, "get", side_effect=updater_values):
        acc_id, acc_name, sso_role, layer_profile = get_layer_profile(
            "project-acc123-devops", updater, "DevOps", "project"
        )

    assert acc_id == "123"
    assert acc_name == "acc123"
    assert sso_role == "devops"
    assert layer_profile == "project-acc123-devops"


NOW_EPOCH = 170500000

FILE_CONFIG_TF = """
provider "aws" {
  region  = var.region
  profile = var.profile
}
"""

FILE_LOCALS_TF = """
provider "aws" {
  region  = var.region
  profile = var.profile
}
"""

FILE_BACKEND_TFVARS = """
profile = "test-apps-devstg-devops"
"""

FILE_AWS_CONFIG = """
[profile test-sso]
sso_region = us-test-1

[profile test-sso-apps-devstg]
account_id = 123
role_name = devops

[profile test-apps-devstg-devops]
expiration=1705859470

[profile test-sso-first]
account_id = 456
role_name = devops

[profile test-sso-valid]
account_id = 789
role_name = devops

[profile test-valid-devops]
expiration=170600900000
"""

FILE_AWS_CREDENTIALS = """
[test-apps-devstg-devops]
aws_access_key_id = access-key
aws_secret_access_key = secret-key
aws_session_token = session-token
"""

data_dict = {
    "config.tf": FILE_CONFIG_TF,
    "locals.tf": FILE_LOCALS_TF,
    "backend.tfvars": FILE_BACKEND_TFVARS,
    "~/.aws/test/config": FILE_AWS_CONFIG,
    "~/.aws/test/credentials": FILE_AWS_CREDENTIALS,
}


def read_text_side_effect(self: PosixPath, *args, **kwargs):
    """
    Every time we call read_text(), this side effect will try to get the value from data_dict rather than reading a disk file.
    Raises FileNotFoundError for unknown files so the caller's `except FileNotFoundError`
    paths (e.g. optional tf files in get_profiles) work as expected.
    """
    try:
        return data_dict[self.name]
    except KeyError:
        raise FileNotFoundError(self.name)


def open_side_effect(name, *args, **kwargs):
    """
    Every time we call open(), this side effect will try to get the value from data_dict rather than reading a disk file.
    Accepts either a string or PosixPath for `name`.
    """
    return mock.mock_open(read_data=data_dict.get(str(name), data_dict.get(name, "")))()


b3_client = Mock()
b3_client.get_role_credentials = Mock(
    return_value={
        "roleCredentials": {
            "expiration": "1705859400",
            "accessKeyId": "access-key",
            "secretAccessKey": "secret-key",
            "sessionToken": "session-token",
        }
    }
)


@mock.patch("leverage.modules.auth.get_profiles", new=Mock(return_value=("test-first-devops", ["test-first-profile"])))
@mock.patch("leverage.modules.auth.get_or_create_section", new=Mock())
@mock.patch.object(aws_module.ConfigUpdater, "update_file", new=Mock())
@mock.patch("pathlib.Path.touch", new=Mock())
@mock.patch("boto3.client", return_value=b3_client)
@mock.patch("configupdater.parser.open", side_effect=open_side_effect)
def test_refresh_layer_credentials_first_time(mock_open, mock_boto, paths, mock_sso_token, caplog):
    refresh_layer_credentials(paths)

    # there was no previous profile set for the layer
    assert "No cached credentials found." in caplog.messages
    # so we retrieve it
    assert "Retrieving role credentials for devops..." in caplog.messages


@mock.patch("leverage.modules.auth.get_profiles", new=Mock(return_value=("test-valid-devops", ["test-valid-profile"])))
@mock.patch("leverage.modules.auth.get_or_create_section", new=Mock())
@mock.patch.object(aws_module.ConfigUpdater, "update_file", new=Mock())
@mock.patch("time.time", new=Mock(return_value=NOW_EPOCH))
@mock.patch("boto3.client", return_value=b3_client)
@mock.patch("configupdater.parser.open", side_effect=open_side_effect)
def test_refresh_layer_credentials_still_valid(mock_open, mock_boto, paths, mock_sso_token, caplog):
    refresh_layer_credentials(paths)

    assert "Token expiration time: 170600900.0" in caplog.messages
    assert "Token renewal time: 170501800" in caplog.messages  # NOW_EPOCH + 30*60
    # renewal is less than expiration, so our credentials are still fine
    assert "Using already configured temporary credentials." in caplog.messages


@mock.patch("leverage.modules.auth.update_config_section")
@mock.patch("pathlib.Path.read_text", new=read_text_side_effect)
@mock.patch("pathlib.Path.touch", new=Mock())
@mock.patch("time.time", new=Mock(return_value=1705859000))
@mock.patch("boto3.client", return_value=b3_client)
@mock.patch("configupdater.parser.open", side_effect=open_side_effect)
def test_refresh_layer_credentials(mock_open, mock_boto, mock_update_conf, paths, mock_sso_token, propagate_logs):
    refresh_layer_credentials(paths)

    # the expiration was set
    assert mock_update_conf.call_args_list[0].args[1] == "profile test-apps-devstg-devops"
    assert mock_update_conf.call_args_list[0].kwargs["data"] == {"expiration": "1705859400"}
    # and the corresponding attributes
    assert mock_update_conf.call_args_list[1].args[1] == "test-apps-devstg-devops"
    assert mock_update_conf.call_args_list[1].kwargs["data"] == {
        "aws_access_key_id": "access-key",
        "aws_secret_access_key": "secret-key",
        "aws_session_token": "session-token",
    }


@mock.patch("leverage.modules.auth.update_config_section")
@mock.patch("pathlib.Path.read_text", new=read_text_side_effect)
@mock.patch("pathlib.Path.touch", new=Mock())
@mock.patch("time.time", new=Mock(return_value=1705859000))
@mock.patch("configupdater.parser.open", side_effect=open_side_effect)
@pytest.mark.parametrize(
    "error",
    [
        ClientError({"Error": {"Code": "AccessDeniedException", "Message": "No access"}}, "GetRoleCredentials"),
        ClientError({"Error": {"Code": "ForbiddenException", "Message": "No access"}}, "GetRoleCredentials"),
    ],
)
def test_refresh_layer_credentials_no_access(mock_open, mock_update_conf, paths, mock_sso_token, error):
    with mock.patch("boto3.client") as mocked_client:
        mocked_client_obj = MagicMock()
        mocked_client_obj.get_role_credentials.side_effect = error
        mocked_client.return_value = mocked_client_obj

        with pytest.raises(ExitError):
            refresh_layer_credentials(paths)


# Tests for refresh_all_accounts_credentials


FILE_AWS_CONFIG_MULTI_ACCOUNTS = """
[profile test-sso]
sso_region = us-test-1

[profile test-sso-security]
account_id = 123456
role_name = DevOps

[profile test-sso-shared]
account_id = 234567
role_name = DevOps

[profile test-sso-network]
account_id = 345678
role_name = DevOps

[profile test-security-devops]
expiration=1705859470

[profile test-shared-devops]
expiration=170600900000

[profile test-network-devops]
"""

data_dict_multi = {
    "~/.aws/test/config": FILE_AWS_CONFIG_MULTI_ACCOUNTS,
    "~/.aws/test/credentials": "",
}


def open_side_effect_multi(name: PosixPath, *_args, **_kwargs):
    """
    Side effect for opening multi-account config files.
    """
    file_content = data_dict_multi.get(str(name), data_dict_multi.get(name, ""))
    return mock.mock_open(read_data=file_content)()


b3_client_multi = Mock()
b3_client_multi.get_role_credentials = Mock(
    return_value={
        "roleCredentials": {
            "expiration": "1705859500",
            "accessKeyId": "new-access-key",
            "secretAccessKey": "new-secret-key",
            "sessionToken": "new-session-token",
        }
    }
)


@mock.patch("leverage.modules.auth.update_config_section")
@mock.patch("pathlib.Path.touch", new=Mock())
@mock.patch("time.time", new=Mock(return_value=NOW_EPOCH))
@mock.patch("boto3.client", return_value=b3_client_multi)
@mock.patch("configupdater.parser.open", side_effect=open_side_effect_multi)
def test_refresh_all_accounts_credentials_success(
    _mock_open, _mock_boto, _mock_update_conf, paths, mock_sso_token, caplog
):
    """
    Test successful credential refresh for multiple accounts with smart expiration checking.

    Verifies:
    1. The function correctly identifies SSO profiles from the config file.
    2. It skips accounts with valid (non-expired) credentials when force_refresh=False.
    3. It refreshes credentials for accounts that need renewal.
    4. It provides clear progress logging for each account.
    5. It returns a summary of successful vs failed operations.
    """
    refresh_all_accounts_credentials(paths, force_refresh=False)

    assert "Refreshing credentials for all accounts..." in caplog.text
    assert "Found 3 account(s) to refresh." in caplog.text

    assert "Retrieving credentials for security account..." in caplog.text
    assert "Credentials for security account refreshed successfully" in caplog.text
    assert "Retrieving credentials for network account..." in caplog.text
    assert "Credentials for network account refreshed successfully" in caplog.text

    assert "Credentials for shared account are still valid, skipping." in caplog.text

    assert "Credential refresh complete: 2 refreshed, 1 skipped, 0 failed." in caplog.text


@mock.patch("pathlib.Path.touch", new=Mock())
@mock.patch("boto3.client", return_value=b3_client_multi)
@mock.patch("configupdater.parser.open", side_effect=open_side_effect_multi)
def test_refresh_all_accounts_credentials_force_refresh(_mock_open, _mock_boto, paths, mock_sso_token, caplog):
    """
    Test that force_refresh=True bypasses expiration checks and refreshes all credentials.
    """
    with mock.patch("leverage.modules.auth.update_config_section"):
        refresh_all_accounts_credentials(paths, force_refresh=True)

    assert "Retrieving credentials for security account..." in caplog.text
    assert "Retrieving credentials for shared account..." in caplog.text
    assert "Retrieving credentials for network account..." in caplog.text

    assert "are still valid, skipping" not in caplog.text


FILE_AWS_CONFIG_NO_SSO_PROFILES = """
[profile test-sso]
sso_region = us-test-1
"""

data_dict_no_profiles = {
    "~/.aws/test/config": FILE_AWS_CONFIG_NO_SSO_PROFILES,
    "~/.aws/test/credentials": "",
}


def open_side_effect_no_profiles(name: PosixPath, *_args, **_kwargs):
    """
    Side effect for opening config with no SSO profiles.
    """
    file_content = data_dict_no_profiles.get(str(name), data_dict_no_profiles.get(name, ""))
    return mock.mock_open(read_data=file_content)()


@mock.patch("pathlib.Path.touch", new=Mock())
@mock.patch("boto3.client", return_value=b3_client_multi)
@mock.patch("configupdater.parser.open", side_effect=open_side_effect_no_profiles)
def test_refresh_all_accounts_credentials_no_profiles(_mock_open, _mock_boto, paths, mock_sso_token, caplog):
    """
    Test graceful handling when no SSO account profiles are configured.
    """
    refresh_all_accounts_credentials(paths, force_refresh=False)

    assert "No SSO account profiles found" in caplog.text


@mock.patch("leverage.modules.auth.update_config_section")
@mock.patch("pathlib.Path.touch", new=Mock())
@mock.patch("time.time", new=Mock(return_value=NOW_EPOCH))
@mock.patch("configupdater.parser.open", side_effect=open_side_effect_multi)
def test_refresh_all_accounts_credentials_permission_error(
    _mock_open, _mock_update_conf, paths, mock_sso_token, caplog
):
    """
    Test graceful handling of permission errors for specific accounts while continuing with others.
    """
    with mock.patch("boto3.client") as mocked_client:
        mocked_client_obj = MagicMock()
        # First call succeeds, second call fails with permission error, third call succeeds
        mocked_client_obj.get_role_credentials.side_effect = [
            {
                "roleCredentials": {
                    "expiration": "1705859500",
                    "accessKeyId": "access-key",
                    "secretAccessKey": "secret-key",
                    "sessionToken": "session-token",
                }
            },
            ClientError({"Error": {"Code": "AccessDeniedException", "Message": "No access"}}, "GetRoleCredentials"),
            {
                "roleCredentials": {
                    "expiration": "1705859500",
                    "accessKeyId": "access-key",
                    "secretAccessKey": "secret-key",
                    "sessionToken": "session-token",
                }
            },
        ]
        mocked_client.return_value = mocked_client_obj

        refresh_all_accounts_credentials(paths, force_refresh=True)

    assert "No permission to assume role" in caplog.text
    assert "Skipping." in caplog.text

    assert "Credential refresh complete: 2 refreshed, 0 skipped, 1 failed." in caplog.text


@mock.patch("pathlib.Path.touch", new=Mock())
@mock.patch("configupdater.parser.open", side_effect=open_side_effect_multi)
def test_refresh_all_accounts_credentials_token_error(_mock_open, paths):
    """
    Test that the function properly handles SSO access token retrieval failures.
    """
    with mock.patch("leverage.modules.auth.get_sso_access_token", side_effect=FileNotFoundError("Token not found")):
        with mock.patch("boto3.client", return_value=b3_client_multi):
            with pytest.raises(ExitError, match="Failed to get SSO access token"):
                refresh_all_accounts_credentials(paths, force_refresh=False)


@mock.patch("leverage.modules.auth.update_config_section")
@mock.patch("pathlib.Path.touch", new=Mock())
@mock.patch("time.time", new=Mock(return_value=NOW_EPOCH))
@mock.patch("boto3.client", return_value=b3_client_multi)
@mock.patch("configupdater.parser.open", side_effect=open_side_effect_multi)
def test_refresh_all_accounts_credentials_calls_update_correctly(
    _mock_open, _mock_boto, mock_update_conf, paths, mock_sso_token
):
    """
    Test that the function correctly updates both AWS config and credentials files with proper data.
    """
    refresh_all_accounts_credentials(paths, force_refresh=True)

    # 3 accounts with force_refresh => 6 calls (config + credentials for each)
    assert mock_update_conf.call_count == 6

    profile_calls = [call.args[1] for call in mock_update_conf.call_args_list]
    assert "profile test-security-devops" in profile_calls
    assert "test-security-devops" in profile_calls
    assert "profile test-shared-devops" in profile_calls
    assert "test-shared-devops" in profile_calls
    assert "profile test-network-devops" in profile_calls
    assert "test-network-devops" in profile_calls


# Integration-style test with real file operations
def test_refresh_all_accounts_credentials_integration(tmp_path, paths, mock_sso_token, caplog):
    """
    Integration test using real file operations to verify end-to-end functionality.
    """
    # Create real temporary files
    config_file = tmp_path / "config"
    credentials_file = tmp_path / "credentials"

    config_content = """[profile test-sso]
sso_region = us-test-1

[profile test-sso-security]
account_id = 123456
role_name = DevOps

[profile test-sso-shared]
account_id = 234567
role_name = DevOps

[profile test-security-devops]
expiration=170600900000
"""
    config_file.write_text(config_content)
    credentials_file.write_text("")

    # Point the mocked PathsHandler at the real files
    paths.aws_config_file = config_file
    paths.aws_credentials_file = credentials_file

    with mock.patch("time.time", return_value=NOW_EPOCH):
        with mock.patch("boto3.client", return_value=b3_client_multi):
            with mock.patch("leverage.modules.auth.update_config_section") as mock_update:
                refresh_all_accounts_credentials(paths, force_refresh=False)

    # Security account should be skipped (valid credentials), shared account should be refreshed
    assert mock_update.call_count == 2  # 1 account refreshed (config + credentials)

    profile_calls = [call.args[1] for call in mock_update.call_args_list]
    assert "profile test-shared-devops" in profile_calls
    assert "test-shared-devops" in profile_calls

    assert "Found 2 account(s) to refresh." in caplog.text
    assert "Credentials for security account are still valid, skipping." in caplog.text
    assert "Retrieving credentials for shared account..." in caplog.text
    assert "Credentials for shared account refreshed successfully." in caplog.text


# CLI-level regression tests for the click subcommand dispatch path.
#
# Before the fix in `leverage.modules.utils._handle_subcommand`, invoking any sso subcommand
# that declared its own click options (e.g. `aws sso login --refresh-all`, `aws sso refresh
# [--force]`) crashed with `TypeError: <cmd>() got an unexpected keyword argument 'args'`
# because `context.forward(subcommand)` was copying the parent group's `args` parameter into
# the child callback's kwargs.


def test_aws_sso_refresh_invokes_refresh_all_accounts(leverage_project, leverage_runner):
    """`leverage aws sso refresh` reaches refresh_all_accounts_credentials with force_refresh=False."""
    with leverage_runner(leverage_project) as runner:
        with mock.patch.object(aws_module, "refresh_all_accounts_credentials") as mock_refresh:
            result = runner.invoke(leverage, ["aws", "sso", "refresh"])

    assert result.exit_code == 0, result.output + (str(result.exception) if result.exception else "")
    mock_refresh.assert_called_once()
    assert mock_refresh.call_args.kwargs == {"force_refresh": False}


def test_aws_sso_refresh_force_invokes_refresh_all_accounts(leverage_project, leverage_runner):
    """`leverage aws sso refresh --force` forwards force_refresh=True."""
    with leverage_runner(leverage_project) as runner:
        with mock.patch.object(aws_module, "refresh_all_accounts_credentials") as mock_refresh:
            result = runner.invoke(leverage, ["aws", "sso", "refresh", "--force"])

    assert result.exit_code == 0, result.output + (str(result.exception) if result.exception else "")
    mock_refresh.assert_called_once()
    assert mock_refresh.call_args.kwargs == {"force_refresh": True}
