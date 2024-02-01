from collections import namedtuple
from unittest import mock
from unittest.mock import Mock, MagicMock, PropertyMock

import pytest
from configupdater import ConfigUpdater

from leverage._utils import ExitError
from leverage.container import SSOContainer
from leverage.modules.auth import refresh_layer_credentials, get_layer_profile, SkipProfile
from leverage.modules.aws import get_account_roles, add_sso_profile, configure_sso_profiles
from tests.test_containers import container_fixture_factory


@pytest.fixture
def sso_container(with_click_context, propagate_logs):
    mocked_cont = container_fixture_factory(SSOContainer)
    mocked_cont.get_sso_access_token = Mock(return_value="testing-token")

    # mock PathsHandler with a named tuple?
    with mock.patch(
        "leverage.container.PathsHandler.local_backend_tfvars",
        new_callable=PropertyMock(return_value="~/config/backend.tfvars"),
    ), mock.patch(
        "leverage.container.PathsHandler.host_aws_profiles_file",
        new_callable=PropertyMock(return_value="~/.aws/test/config"),
    ), mock.patch(
        "leverage.container.PathsHandler.host_aws_credentials_file",
        new_callable=PropertyMock(return_value="~/.aws/test/credentials"),
    ):
        yield mocked_cont


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
    "~/config/backend.tfvars": FILE_BACKEND_TFVARS,
    "~/.aws/test/config": FILE_AWS_CONFIG,
    "~/.aws/test/credentials": FILE_AWS_CREDENTIALS,
}


def open_side_effect(name, *args, **kwargs):
    """
    Everytime we call open(), this side effect will try to get the value from data_dict rather than reading a disk file.
    """
    return mock.mock_open(read_data=data_dict[name])()


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
@mock.patch("leverage.modules.aws.ConfigUpdater.update_file", new=Mock())
@mock.patch("builtins.open", side_effect=open_side_effect)
@mock.patch("boto3.client", return_value=b3_client)
@mock.patch("pathlib.Path.touch", new=Mock())
def test_refresh_layer_credentials_first_time(mock_open, mock_boto, sso_container, caplog):
    refresh_layer_credentials(sso_container)

    # there was no previous profile set for the layer
    assert caplog.messages[1] == "No cached credentials found."
    # so we retrieve it
    assert caplog.messages[2] == "Retrieving role credentials for devops..."


@mock.patch("leverage.modules.auth.get_profiles", new=Mock(return_value=("test-valid-devops", ["test-valid-profile"])))
@mock.patch("leverage.modules.auth.get_or_create_section", new=Mock())
@mock.patch("leverage.modules.aws.ConfigUpdater.update_file", new=Mock())
@mock.patch("builtins.open", side_effect=open_side_effect)
@mock.patch("boto3.client", return_value=b3_client)
@mock.patch("time.time", new=Mock(return_value=NOW_EPOCH))
def test_refresh_layer_credentials_still_valid(mock_open, mock_boto, sso_container, caplog):
    refresh_layer_credentials(sso_container)

    assert caplog.messages[1] == f"Token expiration time: 170600900.0"
    assert caplog.messages[2] == f"Token renewal time: 170501800"  # NOW_EPOCH - 30*60
    # renewal is less than expiration, so our credentials are still fine
    assert caplog.messages[3] == "Using already configured temporary credentials."


@mock.patch("leverage.modules.auth.update_config_section")
@mock.patch("builtins.open", side_effect=open_side_effect)
@mock.patch("boto3.client", return_value=b3_client)
@mock.patch("time.time", new=Mock(return_value=1705859000))
@mock.patch("pathlib.Path.touch", new=Mock())
def test_refresh_layer_credentials(mock_boto, mock_open, mock_update_conf, sso_container, propagate_logs):
    refresh_layer_credentials(sso_container)

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
