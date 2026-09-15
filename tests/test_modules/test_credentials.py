from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from unittest import mock
from unittest.mock import Mock

import click
import pytest

from leverage._internals import State
from leverage._utils import ExitError
from leverage.modules.credentials import (
    _load_configs_for_credentials,
    configure_accounts_profiles,
    _extract_credentials,
    _get_mfa_serial,
    _get_organization_accounts,
    _replace_hcl_attribute,
    configure_credentials,
    _credentials_are_valid,
    _get_management_account_id,
    configure_profile,
    _update_account_ids,
)

# `leverage.modules.credentials` resolves to the click Group of the same name, since it is
# re-exported in `leverage/modules/__init__.py`. Patching by string would target that Group
# instead of the module, so the module itself is imported and patched by object.
credentials_module = import_module("leverage.modules.credentials")


@contextmanager
def cli_context(runner=None, paths=None, config=None, verbose=False):
    """Build a Leverage click context holding the given runner, paths and configuration.

    The credentials module gets all three injected through the `pass_runner`, `pass_paths`
    and `pass_state` decorators, so they must be set on the context state object.
    """
    state = State()
    state.verbosity = verbose
    state.runner = runner
    state.paths = paths
    state.config = config

    with click.Context(command=click.Command("leverage"), obj=state):
        yield


def awscli_returning(exit_code, output):
    """AWS cli runner double whose `exec` returns the given exit code and output."""
    return Mock(exec=Mock(return_value=(exit_code, output, "")))


PROJECT_YAML = {
    "short_name": "test",
    "region": "us-test-1",
    "organization": {"accounts": [{"name": "acc2"}]},
}

ENV_CONFIG = {"PROJECT": "test", "MFA_ENABLED": "true"}

COMMON_CONF = {
    "project_long": "test-prjt",
    "region_secondary": "us-test-2",
    "accounts": {"acc1": {"email": "test@test.com", "id": "123456"}},
}


@mock.patch.object(credentials_module, "_load_project_yaml", Mock(return_value=PROJECT_YAML))
def test_load_configs_for_credentials():
    """
    Test that the values needed to configure the credentials are gathered from the project
    configuration file, the build.env config and the tf common configuration.
    """
    with cli_context(paths=Mock(common_conf=COMMON_CONF), config=ENV_CONFIG):
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


@mock.patch.object(credentials_module, "_get_mfa_serial", new=Mock(return_value="mfa123"))
@mock.patch.object(credentials_module.shutil, "copy")
def test_configure_accounts_profiles(mocked_copy):
    """
    Test that the expected jsons for the aws credentials are generated as expected.
    No-mfa case.
    """
    paths = Mock()
    with cli_context(paths=paths):
        with mock.patch.object(credentials_module, "configure_profile") as mocked_config:
            configure_accounts_profiles(
                "test-management",
                "us-test-1",
                {"acc1": "12345", "out-of-project-acc": "67890"},
                [{"name": "acc1"}],
                fetch_mfa_device=False,
            )

    # make sure we did a backup of the previous account profiles
    mocked_copy.assert_called_once_with(paths.aws_config_file, paths.aws_config_file.with_suffix(".bkp"))

    # only 1 call since "out-of-project-acc" should be avoided
    assert mocked_config.call_count == 1
    assert mocked_config.call_args_list[0][0][0] == "test-acc1-oaar-mfa"
    expected = {
        "output": "json",
        "region": "us-test-1",
        "role_arn": "arn:aws:iam::12345:role/OrganizationAccountAccessRole",
        "source_profile": "test-management",
    }

    assert mocked_config.call_args_list[0][0][1] == expected


@mock.patch.object(credentials_module, "_get_mfa_serial", new=Mock(return_value="mfa123"))
@mock.patch.object(credentials_module.shutil, "copy")
def test_configure_accounts_profiles_mfa(mocked_copy):
    """
    Test that the expected jsons for the aws credentials are generated as expected.
    Mfa case.
    """
    paths = Mock()
    with cli_context(paths=paths):
        with mock.patch.object(credentials_module, "configure_profile") as mocked_config:
            configure_accounts_profiles(
                "test-management",
                "us-test-1",
                {"acc1": "12345", "out-of-project-acc": "67890"},
                [{"name": "acc1"}],
                fetch_mfa_device=True,
            )

    # make sure we did a backup of the previous account profiles
    mocked_copy.assert_called_once_with(paths.aws_config_file, paths.aws_config_file.with_suffix(".bkp"))

    # only 1 call since "out-of-project-acc" should be avoided
    assert mocked_config.call_count == 1
    assert mocked_config.call_args_list[0][0][0] == "test-acc1-oaar-mfa"
    expected = {
        "output": "json",
        "region": "us-test-1",
        "role_arn": "arn:aws:iam::12345:role/OrganizationAccountAccessRole",
        "source_profile": "test-management",
        "mfa_serial": "mfa123",
    }

    assert mocked_config.call_args_list[0][0][1] == expected


@mock.patch.object(credentials_module, "_get_mfa_serial", new=Mock(return_value=""))
def test_configure_accounts_profiles_mfa_error():
    """
    Test that if we fail to fetch the MFA serial number, user get a proper error.
    """
    with cli_context(paths=Mock()):
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
    awscli = awscli_returning(0, '{"Accounts": [{"Name": "test-acc1", "Id": "12345"}]}')
    with cli_context(runner=awscli):
        assert _get_organization_accounts("foo", "bar") == {"test-acc1": "12345"}


def test_get_organization_accounts_error():
    """
    Test that, if getting the list of accounts fails for some reason, we return an empty dict.
    """
    awscli = awscli_returning(1, "BAD")
    with cli_context(runner=awscli):
        assert _get_organization_accounts("foo", "bar") == {}


def test_get_mfa_serial():
    """
    Test that we fetch the mfa devices from the profile and return the serial number of the first one that is valid.
    """
    awscli = awscli_returning(0, '{"MFADevices": [{"SerialNumber": "arn:aws:iam::123456789012:mfa/testuser"}]}')
    with cli_context(runner=awscli):
        assert _get_mfa_serial("foo") == "arn:aws:iam::123456789012:mfa/testuser"


def test_get_mfa_serial_error():
    """
    Test that, if fetching mfa devices fails, we return a user-friendly error.
    """
    awscli = awscli_returning(1, "BAD")
    with cli_context(runner=awscli):
        with pytest.raises(ExitError, match="AWS CLI error: BAD"):
            _get_mfa_serial("foo")


def test_credentials_are_valid():
    """
    Test that AWS credentials for the current profile are valid.
    """
    awscli = awscli_returning(0, "OK")
    with cli_context(runner=awscli):
        assert _credentials_are_valid("foo")


def test_credentials_are_not_valid():
    """
    Test that an invalid security token is reported as invalid credentials.
    """
    awscli = awscli_returning(
        255,
        "An error occurred (InvalidClientTokenId) when calling the GetCallerIdentity operation:"
        " The security token included in the request is invalid.",
    )
    with cli_context(runner=awscli):
        assert not _credentials_are_valid("foo")


def test_get_management_account_id():
    """
    Test that we can get the account id from the current profile.
    """
    awscli = awscli_returning(0, '{"Account": "123456789012"}')
    with cli_context(runner=awscli):
        assert _get_management_account_id("foo") == "123456789012"


def test_get_management_account_id_error():
    """
    Test that we return a user-friendly error if getting the account id of a profile fails.
    """
    awscli = awscli_returning(1, "BAD")
    with cli_context(runner=awscli):
        with pytest.raises(ExitError, match="AWS CLI error: BAD"):
            _get_management_account_id("foo")


def test_configure_profile():
    """
    Test that every value of a profile is set through the AWS cli.
    """
    awscli = awscli_returning(0, "")
    with cli_context(runner=awscli):
        configure_profile("test-acc1-oaar-mfa", {"region": "us-test-1", "output": "json"})

    assert awscli.exec.call_args_list == [
        mock.call("configure", "set", "region", "us-test-1", "--profile", "test-acc1-oaar-mfa"),
        mock.call("configure", "set", "output", "json", "--profile", "test-acc1-oaar-mfa"),
    ]


@mock.patch.object(credentials_module, "_ask_for_credentials", new=Mock(return_value=("foo", "bar")))
@mock.patch.object(credentials_module.shutil, "copy")
def test_configure_credentials(mocked_copy, propagate_logs, caplog):
    """
    Test that the aws credentials for the profile are set and the backup feature is called.
    """
    paths = Mock()
    with cli_context(runner=awscli_returning(0, ""), paths=paths, verbose=True):
        configure_credentials("foo", "manual", make_backup=True)

    assert caplog.messages[0] == "Backing up credentials file."
    mocked_copy.assert_called_once_with(paths.aws_credentials_file, paths.aws_credentials_file.with_suffix(".bkp"))


@mock.patch.object(credentials_module, "_extract_credentials", new=Mock(return_value=("foo", "bar")))
def test_configure_credentials_error():
    """
    Test that, if settings the credentials for a profile fails, we return a user-friendly error.
    """
    with cli_context(runner=awscli_returning(1, "BROKEN"), paths=Mock()):
        with pytest.raises(ExitError, match="AWS CLI error: BROKEN"):
            configure_credentials("foo", "/.aws/creds")


def test_update_account_ids(tmp_path):
    """
    Test that account ids are updated in global configuration files, replacing the whole
    previous `accounts` block and leaving the rest of the file untouched.
    """
    common_tfvars = tmp_path / "common.tfvars"
    common_tfvars.write_text(
        'project = "bb"\n'
        "\n"
        "accounts = {\n"
        "  old = {\n"
        '    email = "old@test.com",\n'
        '    id    = "00000"\n'
        "  },\n"
        "  other = {\n"
        '    email = "other@test.com",\n'
        '    id    = "11111"\n'
        "  }\n"
        "}\n"
        "\n"
        'region_primary = "us-east-1"\n'
    )

    with cli_context(paths=Mock(common_tfvars=common_tfvars)):
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

    assert common_tfvars.read_text() == (
        'project = "bb"\n'
        "\n"
        "accounts = {\n"
        "  acc1 = {\n"
        '    email = "acc@test.com",\n'
        '    id = "12345"\n'
        "  }\n"
        "}\n"
        "\n"
        'region_primary = "us-east-1"\n'
    )


def test_update_account_ids_without_common_tfvars(tmp_path):
    """
    Test that nothing is attempted when the common tfvars file does not exist.
    """
    with cli_context(paths=Mock(common_tfvars=tmp_path / "missing.tfvars")):
        _update_account_ids({"organization": {"accounts": []}})


def test_replace_hcl_attribute_honors_nested_blocks():
    """
    Test that the whole nested block is replaced. A non-greedy regex stops at the first closing
    brace, orphaning the remaining entries and leaving the file with unbalanced braces.
    """
    content = (
        "accounts = {\n"
        "  first = {\n"
        '    id = "1"\n'
        "  },\n"
        "  second = {\n"
        '    id = "2"\n'
        "  }\n"
        "}\n"
        "\n"
        'region = "us-east-1"\n'
    )

    replaced = _replace_hcl_attribute(content, "accounts", '{\n  only = {\n    id = "3"\n  }\n}')

    assert replaced == ("accounts = {\n" "  only = {\n" '    id = "3"\n' "  }\n" "}\n" "\n" 'region = "us-east-1"\n')
    assert replaced.count("{") == replaced.count("}")


def test_replace_hcl_attribute_ignores_similarly_named_attributes():
    """
    Test that an attribute whose name ends with the target one is not replaced.
    """
    content = (
        'external_accounts = {\n  drata = {\n    id = "1"\n  }\n}\n\naccounts = {\n  old = {\n    id = "2"\n  }\n}\n'
    )

    replaced = _replace_hcl_attribute(content, "accounts", '{\n  new = {\n    id = "3"\n  }\n}')

    assert 'external_accounts = {\n  drata = {\n    id = "1"\n  }\n}' in replaced
    assert 'accounts = {\n  new = {\n    id = "3"\n  }\n}' in replaced


def test_replace_hcl_attribute_missing_attribute():
    """
    Test that content without the attribute is returned unchanged.
    """
    content = 'project = "bb"\n'

    assert _replace_hcl_attribute(content, "accounts", "{}") == content
