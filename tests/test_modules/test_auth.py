"""
Tests for leverage/modules/auth.py: the SSO token check, and the SSO and MFA credential refresh that
runs before every tofu/terraform command in a layer.

They run against a real project in tmp_path, through a real PathsHandler, reading and writing real
AWS config, credentials, token and cache files under an isolated HOME. AWS is faked at the API:
real boto3 `sso` and `sts` clients under `botocore.stub.Stubber`, which checks operation names,
request parameters and response shapes against the service models. The Stubber also fails any call
a test has not queued a response for, so "no call was made" is asserted for free.
"""

import importlib
import json
import time
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
import hcl2
import pytest
from botocore.stub import ANY, Stubber
from configupdater import ConfigUpdater

from leverage import conf
from leverage import path as lepath
from leverage._utils import ExitError
from leverage.modules.auth import (
    SkipProfile,
    _perform_authentication,
    check_sso_token,
    get_layer_profile,
    get_profiles,
    refresh_all_accounts_credentials,
    refresh_layer_credentials,
    refresh_layer_credentials_mfa,
)
from leverage.path import PathsHandler

auth_module = importlib.import_module("leverage.modules.auth")

REGION = "us-east-1"
ACCESS_TOKEN = "the-access-token"

COMMON_TFVARS = f"""
project       = "bb"
project_long  = "binbash"
sso_enabled   = true
sso_region    = "{REGION}"
sso_start_url = "https://bb.awsapps.com/start"
"""

# The layer's provider profiles: its own account (from backend.tfvars) and a cross-account one
LAYER_CONFIG_TF = """
terraform {
  backend "s3" {
    key = "account/us-east-1/security-base/terraform.tfstate"
  }
}

provider "aws" {
  region  = var.region
  profile = var.profile
}

provider "aws" {
  alias   = "shared"
  region  = var.region
  profile = "${var.project}-shared-devops"
}
"""

SSO_PROFILES = {
    "profile bb-sso": {"sso_region": REGION, "sso_start_url": "https://bb.awsapps.com/start"},
    "profile bb-sso-account": {"account_id": "111111111111", "role_name": "DevOps"},
    "profile bb-sso-shared": {"account_id": "222222222222", "role_name": "DevOps"},
}


# ###########################################################################
# FIXTURES AND HELPERS
# ###########################################################################
@pytest.fixture
def paths(leverage_project, tmp_path, monkeypatch, propagate_logs):
    """A real PathsHandler, on the security-base layer of a project with SSO enabled."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for var in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")

    (leverage_project / "config" / "common.tfvars").write_text(COMMON_TFVARS)
    (leverage_project / "account" / "config" / "backend.tfvars").write_text(
        'profile = "bb-account-devops"\nbucket = "bb-account-terraform-backend"\nregion = "us-east-1"\n'
    )
    layer = leverage_project / "account" / "us-east-1" / "security-base"
    (layer / "config.tf").write_text(LAYER_CONFIG_TF)

    monkeypatch.setattr(lepath, "get_root_path", lambda: leverage_project)
    monkeypatch.setattr(lepath, "get_working_path", lambda: layer)
    monkeypatch.setattr(conf, "get_root_path", lambda: leverage_project)
    monkeypatch.setattr(conf, "get_working_path", lambda: layer)
    monkeypatch.setattr(Path, "cwd", lambda: layer)

    paths = PathsHandler(conf.load())
    assert paths.aws_credentials_dir == home / ".aws" / "bb"
    return paths


@pytest.fixture
def stubs(monkeypatch):
    """Real `sso` and `sts` clients under a Stubber, returned by boto3.client / boto3.Session."""
    clients = {service: boto3.session.Session().client(service, region_name=REGION) for service in ("sso", "sts")}
    stubbers = {service: Stubber(client) for service, client in clients.items()}

    def client(service, region_name=None, **kwargs):
        assert region_name == REGION, f"{service} client created for region {region_name}"
        return clients[service]

    class Session:
        """Stands in for the boto3.Session the MFA flow builds on the source profile."""

        def __init__(self, botocore_session=None, profile_name=None):
            self.profile_name = profile_name
            sessions.append(profile_name)

        def client(self, service, **kwargs):
            return clients[service]

    sessions = []
    # The layer's profiles come from a set, so their order varies: record which accounts were asked
    requested = []
    clients["sso"].meta.events.register(
        "before-parameter-build.sso.GetRoleCredentials", lambda params, **kwargs: requested.append(params["accountId"])
    )
    monkeypatch.setattr(auth_module.boto3, "client", client)
    monkeypatch.setattr(auth_module.boto3, "Session", Session)
    for stubber in stubbers.values():
        stubber.activate()
    stubbers["sessions"] = sessions
    stubbers["requested_accounts"] = requested
    yield stubbers
    for service in ("sso", "sts"):
        stubbers[service].assert_no_pending_responses()
        stubbers[service].deactivate()


@pytest.fixture
def local_timezone(monkeypatch):
    """Set the process' local timezone; restored after the test."""

    def set_timezone(name):
        monkeypatch.setenv("TZ", name)
        time.tzset()

    yield set_timezone
    monkeypatch.undo()
    time.tzset()


def write_ini(path, sections):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for section, values in sections.items():
        lines.append(f"[{section}]")
        lines.extend(f"{key} = {value}" for key, value in values.items())
        lines.append("")
    path.write_text("\n".join(lines))


def read_ini(path):
    updater = ConfigUpdater()
    updater.read(path)
    return {section: {k: v.value for k, v in updater[section].items()} for section in updater.sections()}


def write_token(paths, expires_at, name="token"):
    paths.sso_cache.mkdir(parents=True, exist_ok=True)
    (paths.sso_cache / name).write_text(
        json.dumps({"accessToken": ACCESS_TOKEN, "expiresAt": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ")})
    )


def epoch_ms(delta):
    """Epoch in milliseconds, `delta` from now: the format of SSO role credentials' expiration."""
    return int((datetime.now(timezone.utc) + delta).timestamp() * 1000)


def role_credentials(name, expiration):
    return {
        "roleCredentials": {
            "accessKeyId": f"AKIA{name.upper()}",
            "secretAccessKey": f"secret-{name}",
            "sessionToken": f"session-{name}",
            "expiration": expiration,
        }
    }


def stub_role_credentials(sso, account_id, name, expiration):
    """Queue a get_role_credentials response. `account_id` may be ANY when the order of the calls
    is not known (see `requested_accounts` in the stubs fixture)."""
    sso.add_response(
        "get_role_credentials",
        role_credentials(name, expiration),
        {"roleName": "DevOps", "accountId": account_id, "accessToken": ACCESS_TOKEN},
    )


def stub_role_credentials_error(sso, account_id, code):
    sso.add_client_error(
        "get_role_credentials",
        service_error_code=code,
        service_message="No access",
        http_status_code=403,
        expected_params={"roleName": "DevOps", "accountId": account_id, "accessToken": ACCESS_TOKEN},
    )


# ###########################################################################
# get_layer_profile
# ###########################################################################
@pytest.mark.parametrize("profile", ["local.account.profile", "${local.profile}-test-devops"])
def test_get_layer_profile_skips_local_references(profile):
    with pytest.raises(SkipProfile):
        get_layer_profile(profile, ConfigUpdater(), "DevOps", "project")


def test_get_layer_profile_requires_the_sso_profile_of_the_account(muted_click_context):
    with pytest.raises(ExitError, match="Missing project-sso-acc123 permission for account acc123."):
        get_layer_profile("project-acc123-devops", ConfigUpdater(), "DevOps", "project")


def test_get_layer_profile(muted_click_context):
    updater = ConfigUpdater()
    updater.read_string("[profile project-sso-acc123]\naccount_id = 123\nrole_name = DevOps\n")

    assert get_layer_profile("${var.project}-acc123-devops", updater, "project-acc123-devops", "project") == (
        "123",
        "acc123",
        "DevOps",
        "project-acc123-devops",
    )


@pytest.mark.parametrize("reference", ["var.profile", "each.value.profile"])
def test_get_layer_profile_of_the_layer_is_the_backend_profile(muted_click_context, reference):
    """A provider on the layer's own profile gets the profile of backend.tfvars, even when it doesn't follow the
    <project>-<account>-<role> convention."""
    updater = ConfigUpdater()
    updater.read_string("[profile project-sso-acc123]\naccount_id = 123\nrole_name = DevOps\n")
    # What the HCL parser returns for `profile = var.profile`
    raw_profile = hcl2_profile(reference)

    assert get_layer_profile(raw_profile, updater, "project-acc123-admin", "project") == (
        "123",
        "acc123",
        "DevOps",
        "project-acc123-admin",
    )


def hcl2_profile(reference):
    """The value the HCL parser gives a provider's `profile = <reference>`."""
    return hcl2.loads(f'provider "aws" {{\n  profile = {reference}\n}}\n')["provider"][0]["aws"]["profile"]


def test_get_profiles_reads_config_locals_and_runtime(paths):
    (paths.cwd / "config.tf").unlink()
    (paths.cwd / "locals.tf").write_text(
        'locals {\n  shared = {\n    profile = "${var.project}-shared-devops"\n  }\n}\n'
    )
    (paths.cwd / "runtime.tf").write_text(
        'provider "aws" {\n  alias   = "network"\n  profile = "bb-network-devops"\n}\n'
    )

    assert get_profiles(paths) == ("bb-account-devops", {"${var.project}-shared-devops", "bb-network-devops"})


# ###########################################################################
# check_sso_token
# ###########################################################################
def test_check_sso_token_requires_a_token(paths):
    with pytest.raises(ExitError, match="No AWS SSO token found") as error:
        check_sso_token(paths)

    assert error.value.exit_code == 1


def test_check_sso_token_rejects_another_accounts_token(paths):
    write_token(paths, datetime.now(timezone.utc) + timedelta(hours=1), name="another-role")

    with pytest.raises(ExitError, match="No valid AWS SSO token found for current account") as error:
        check_sso_token(paths)

    assert error.value.exit_code == 1


def test_check_sso_token_accepts_a_valid_token(paths):
    write_token(paths, datetime.now(timezone.utc) + timedelta(hours=1))

    check_sso_token(paths)


def test_check_sso_token_rejects_an_expired_token(paths):
    write_token(paths, datetime.now(timezone.utc) - timedelta(minutes=1))

    with pytest.raises(ExitError, match="AWS SSO token has expired") as error:
        check_sso_token(paths)

    assert error.value.exit_code == 1


@pytest.mark.parametrize(
    "timezone_name, expires_in, valid",
    [
        # UTC-3: compared against local time, a token expired an hour ago looked valid for 2 more hours
        ("America/Argentina/Buenos_Aires", timedelta(hours=-1), False),
        # UTC+9: compared against local time, a token valid for 2 more hours looked expired
        ("Asia/Tokyo", timedelta(hours=2), True),
    ],
)
def test_check_sso_token_expiry_does_not_depend_on_the_local_timezone(
    paths, local_timezone, timezone_name, expires_in, valid
):
    # The token's expiresAt is in UTC
    write_token(paths, datetime.now(timezone.utc) + expires_in)
    local_timezone(timezone_name)

    if valid:
        check_sso_token(paths)
    else:
        with pytest.raises(ExitError, match="AWS SSO token has expired"):
            check_sso_token(paths)


# ###########################################################################
# _perform_authentication (the `authenticate` decorator of tofu/terraform commands)
# ###########################################################################
@pytest.mark.parametrize(
    "location, common_conf, mfa_enabled, expected",
    [
        ("layer", {"sso_enabled": True}, False, ["check_sso_token", "refresh_layer_credentials"]),
        # SSO wins over MFA
        ("layer", {"sso_enabled": True}, True, ["check_sso_token", "refresh_layer_credentials"]),
        ("layer", {"sso_enabled": False}, True, ["refresh_layer_credentials_mfa"]),
        ("layer", {}, True, ["refresh_layer_credentials_mfa"]),
        ("layer", {}, False, []),
        # Credentials are per layer: anywhere else, nothing to refresh
        ("account", {"sso_enabled": True}, True, []),
        ("root", {"sso_enabled": True}, True, []),
    ],
)
def test_perform_authentication(monkeypatch, location, common_conf, mfa_enabled, expected):
    called = []
    for name in ("check_sso_token", "refresh_layer_credentials", "refresh_layer_credentials_mfa"):
        monkeypatch.setattr(auth_module, name, lambda paths, name=name: called.append((name, paths)))
    paths = SimpleNamespace(get_location_type=lambda: location, common_conf=common_conf, mfa_enabled=mfa_enabled)

    _perform_authentication(paths)

    assert called == [(name, paths) for name in expected]


# ###########################################################################
# refresh_layer_credentials (SSO)
# ###########################################################################
def set_layer_profiles(paths, *profiles):
    """Rewrite the layer's config.tf with one aws provider per profile expression."""
    providers = "\n".join(
        f'provider "aws" {{\n  alias   = "p{index}"\n  region  = var.region\n  profile = {profile}\n}}\n'
        for index, profile in enumerate(profiles)
    )
    (paths.cwd / "config.tf").write_text('terraform {\n  backend "s3" {}\n}\n\n' + providers)


def test_refresh_layer_credentials_writes_the_credentials_of_every_layer_profile(paths, stubs):
    write_ini(paths.aws_config_file, SSO_PROFILES)
    write_token(paths, datetime.now(timezone.utc) + timedelta(hours=1))
    expiration = epoch_ms(timedelta(hours=1))
    for _ in range(2):
        stub_role_credentials(stubs["sso"], ANY, "role", expiration)

    refresh_layer_credentials(paths)

    # The layer's own account (from backend.tfvars) and the cross-account provider
    assert sorted(stubs["requested_accounts"]) == ["111111111111", "222222222222"]
    # Only their owner can read the credentials, as the AWS CLI does
    assert paths.aws_credentials_file.stat().st_mode & 0o777 == 0o600
    config = read_ini(paths.aws_config_file)
    credentials = read_ini(paths.aws_credentials_file)
    for profile in ("bb-account-devops", "bb-shared-devops"):
        assert config[f"profile {profile}"] == {"expiration": str(expiration)}
        assert credentials[profile] == {
            "aws_access_key_id": "AKIAROLE",
            "aws_secret_access_key": "secret-role",
            "aws_session_token": "session-role",
        }
    # The SSO profiles are left as they were
    for section, values in SSO_PROFILES.items():
        assert config[section] == values


def test_refresh_layer_credentials_writes_the_layer_profile_of_backend_tfvars(paths, stubs):
    """`profile = var.profile` is the profile of backend.tfvars, the one tofu looks up, whatever its name."""
    (paths.cwd.parent.parent / "config" / "backend.tfvars").write_text(
        'profile = "bb-account-admin"\nbucket = "bb-account-terraform-backend"\nregion = "us-east-1"\n'
    )
    paths = PathsHandler(conf.load())
    set_layer_profiles(paths, "var.profile")
    write_ini(paths.aws_config_file, SSO_PROFILES)
    write_token(paths, datetime.now(timezone.utc) + timedelta(hours=1))
    stub_role_credentials(stubs["sso"], "111111111111", "account", epoch_ms(timedelta(hours=1)))

    refresh_layer_credentials(paths)

    assert set(read_ini(paths.aws_credentials_file)) == {"bb-account-admin"}


def test_refresh_layer_credentials_skips_local_references_and_valid_profiles_and_goes_on(paths, stubs, monkeypatch):
    # A list, not a set, so the local reference and the still valid profile come first
    monkeypatch.setattr(
        auth_module,
        "get_profiles",
        lambda paths: ("bb-account-devops", ["${local.profile}", "${var.project}-shared-devops", "${var.profile}"]),
    )
    write_ini(
        paths.aws_config_file,
        {**SSO_PROFILES, "profile bb-shared-devops": {"expiration": epoch_ms(timedelta(hours=2))}},
    )
    write_token(paths, datetime.now(timezone.utc) + timedelta(hours=1))
    stub_role_credentials(stubs["sso"], "111111111111", "account", epoch_ms(timedelta(hours=1)))

    refresh_layer_credentials(paths)

    assert set(read_ini(paths.aws_credentials_file)) == {"bb-account-devops"}


def test_refresh_layer_credentials_keeps_credentials_that_are_still_valid(paths, stubs):
    still_valid = epoch_ms(timedelta(hours=2))
    write_ini(
        paths.aws_config_file,
        {
            **SSO_PROFILES,
            "profile bb-account-devops": {"expiration": still_valid},
            "profile bb-shared-devops": {"expiration": still_valid},
        },
    )
    write_token(paths, datetime.now(timezone.utc) + timedelta(hours=1))

    # No get_role_credentials queued: any call would fail
    refresh_layer_credentials(paths)

    assert not paths.aws_credentials_file.exists()


def test_refresh_layer_credentials_renews_credentials_about_to_expire(paths, stubs):
    # Within the 30 minutes margin, so a long apply does not run out of credentials
    set_layer_profiles(paths, "var.profile")
    write_ini(
        paths.aws_config_file,
        {**SSO_PROFILES, "profile bb-account-devops": {"expiration": epoch_ms(timedelta(minutes=10))}},
    )
    write_token(paths, datetime.now(timezone.utc) + timedelta(hours=1))
    expiration = epoch_ms(timedelta(hours=1))
    stub_role_credentials(stubs["sso"], "111111111111", "account", expiration)

    refresh_layer_credentials(paths)

    assert read_ini(paths.aws_config_file)["profile bb-account-devops"] == {"expiration": str(expiration)}
    assert read_ini(paths.aws_credentials_file)["bb-account-devops"]["aws_access_key_id"] == "AKIAACCOUNT"


def test_refresh_layer_credentials_requires_the_sso_profile_of_each_account(paths, stubs):
    set_layer_profiles(paths, '"${var.project}-shared-devops"')
    write_ini(paths.aws_config_file, {k: v for k, v in SSO_PROFILES.items() if k != "profile bb-sso-shared"})
    write_token(paths, datetime.now(timezone.utc) + timedelta(hours=1))

    with pytest.raises(ExitError, match="Missing bb-sso-shared permission for account shared") as error:
        refresh_layer_credentials(paths)

    assert error.value.exit_code == 40


@pytest.mark.parametrize(
    "code, exit_code, message",
    [
        ("ForbiddenException", 40, "User does not have permission to assume role"),
        ("AccessDeniedException", 40, "User does not have permission to assume role"),
        # e.g. the SSO token was revoked
        ("UnauthorizedException", 50, "Error retrieving role credentials"),
    ],
)
def test_refresh_layer_credentials_reports_sso_errors(paths, stubs, code, exit_code, message):
    set_layer_profiles(paths, "var.profile")
    write_ini(paths.aws_config_file, SSO_PROFILES)
    write_token(paths, datetime.now(timezone.utc) + timedelta(hours=1))
    stub_role_credentials_error(stubs["sso"], "111111111111", code)

    with pytest.raises(ExitError, match=message) as error:
        refresh_layer_credentials(paths)

    assert error.value.exit_code == exit_code


# ###########################################################################
# refresh_all_accounts_credentials (`leverage aws sso refresh`, `login --refresh-all`)
# ###########################################################################
ALL_ACCOUNTS_PROFILES = {
    **SSO_PROFILES,
    "profile bb-sso-security": {"account_id": "333333333333", "role_name": "DevOps"},
}


def test_refresh_all_accounts_counts_every_account(paths, stubs, caplog):
    still_valid = epoch_ms(timedelta(hours=2))
    write_ini(
        paths.aws_config_file,
        {
            **ALL_ACCOUNTS_PROFILES,
            "profile bb-sso-network": {"account_id": "444444444444", "role_name": "DevOps"},
            "profile bb-account-devops": {"expiration": still_valid},
            "profile bb-shared-devops": {"expiration": still_valid},
        },
    )
    write_token(paths, datetime.now(timezone.utc) + timedelta(hours=1))
    stub_role_credentials_error(stubs["sso"], "333333333333", "ForbiddenException")
    stub_role_credentials_error(stubs["sso"], "444444444444", "AccessDeniedException")

    refresh_all_accounts_credentials(paths)

    assert "Credential refresh complete: 0 refreshed, 2 skipped, 2 failed." in caplog.messages


def test_refresh_all_accounts_renews_expired_skips_valid_and_survives_denied(paths, stubs, caplog):
    write_ini(
        paths.aws_config_file,
        {
            **ALL_ACCOUNTS_PROFILES,
            "profile bb-account-devops": {"expiration": epoch_ms(timedelta(hours=-1))},
            "profile bb-shared-devops": {"expiration": epoch_ms(timedelta(hours=2))},
        },
    )
    write_token(paths, datetime.now(timezone.utc) + timedelta(hours=1))
    # In the order of the config file: account, (shared is still valid), security
    stub_role_credentials(stubs["sso"], "111111111111", "account", epoch_ms(timedelta(hours=1)))
    stub_role_credentials_error(stubs["sso"], "333333333333", "ForbiddenException")

    refresh_all_accounts_credentials(paths)

    credentials = read_ini(paths.aws_credentials_file)
    assert set(credentials) == {"bb-account-devops"}
    assert "No permission to assume role [bold]DevOps[/bold] in security account. Skipping." in caplog.messages
    assert "Credential refresh complete: 1 refreshed, 1 skipped, 1 failed." in caplog.messages


def test_refresh_all_accounts_force_renews_valid_credentials_too(paths, stubs, caplog):
    write_ini(
        paths.aws_config_file,
        {**ALL_ACCOUNTS_PROFILES, "profile bb-shared-devops": {"expiration": epoch_ms(timedelta(hours=2))}},
    )
    write_token(paths, datetime.now(timezone.utc) + timedelta(hours=1))
    for account_id, name in (("111111111111", "account"), ("222222222222", "shared"), ("333333333333", "security")):
        stub_role_credentials(stubs["sso"], account_id, name, epoch_ms(timedelta(hours=1)))

    refresh_all_accounts_credentials(paths, force_refresh=True)

    assert set(read_ini(paths.aws_credentials_file)) == {"bb-account-devops", "bb-shared-devops", "bb-security-devops"}
    assert "Credential refresh complete: 3 refreshed, 0 skipped, 0 failed." in caplog.messages


def test_refresh_all_accounts_without_account_profiles(paths, stubs, caplog):
    write_ini(paths.aws_config_file, {"profile bb-sso": SSO_PROFILES["profile bb-sso"]})

    refresh_all_accounts_credentials(paths)

    assert "No SSO account profiles found. Run 'leverage aws configure sso' first." in caplog.messages
    assert not paths.aws_credentials_file.exists()


def test_refresh_all_accounts_requires_a_token(paths, stubs):
    write_ini(paths.aws_config_file, ALL_ACCOUNTS_PROFILES)

    with pytest.raises(ExitError, match="Failed to get SSO access token") as error:
        refresh_all_accounts_credentials(paths)

    assert error.value.exit_code == 1


# ###########################################################################
# refresh_layer_credentials_mfa
# ###########################################################################
ROLE_ARN = "arn:aws:iam::111111111111:role/DevOps"
MFA_SERIAL = "arn:aws:iam::000000000000:mfa/john"

MFA_PROFILES = {
    "profile bb-account-devops-mfa": {
        "role_arn": ROLE_ARN,
        "mfa_serial": MFA_SERIAL,
        "source_profile": "bb-management-oaar",
    },
}

ASSUME_ROLE_PARAMS = {
    "RoleArn": ROLE_ARN,
    "RoleSessionName": "leverage-bb-account-devops",
    "SerialNumber": MFA_SERIAL,
    "TokenCode": ANY,
}


@pytest.fixture
def mfa_codes(monkeypatch):
    """The MFA codes the user types, in order. Records how many times they were asked."""
    codes = []
    asked = []

    def prompt(text, **kwargs):
        asked.append(text)
        return codes.pop(0)

    monkeypatch.setattr(auth_module.click, "prompt", prompt)
    return codes, asked


def stub_assume_role(sts, token_code="123456"):
    expiration = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(microsecond=0)
    sts.add_response(
        "assume_role",
        {
            "Credentials": {
                "AccessKeyId": "AKIAIOSFODNN7EXAMPLE",
                "SecretAccessKey": "the-secret-access-key",
                "SessionToken": "the-session-token",
                "Expiration": expiration,
            }
        },
        {**ASSUME_ROLE_PARAMS, "TokenCode": token_code},
    )
    return expiration


def stub_assume_role_error(sts, code, message):
    sts.add_client_error(
        "assume_role",
        service_error_code=code,
        service_message=message,
        http_status_code=403,
        expected_params=ASSUME_ROLE_PARAMS,
    )


@pytest.fixture
def mfa_layer(paths):
    set_layer_profiles(paths, "var.profile")
    write_ini(paths.aws_config_file, MFA_PROFILES)
    return paths


def test_mfa_assumes_the_role_and_writes_and_caches_the_credentials(mfa_layer, stubs, mfa_codes):
    codes, asked = mfa_codes
    codes.append("123456")
    expiration = stub_assume_role(stubs["sts"])

    refresh_layer_credentials_mfa(mfa_layer)

    assert asked == ["Enter MFA token code"]
    # The role is assumed with the source profile's credentials
    assert stubs["sessions"] == ["bb-management-oaar"]
    assert read_ini(mfa_layer.aws_credentials_file)["bb-account-devops"] == {
        "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "aws_secret_access_key": "the-secret-access-key",
        "aws_session_token": "the-session-token",
    }
    cached = json.loads((mfa_layer.aws_cache_dir / "bb-account-devops").read_text())
    assert cached["Expiration"] == expiration.strftime("%Y-%m-%dT%H:%M:%SZ")
    # Only their owner can read the credentials and their cache
    assert mfa_layer.aws_credentials_file.stat().st_mode & 0o777 == 0o600
    assert mfa_layer.aws_cache_dir.stat().st_mode & 0o777 == 0o700
    assert (mfa_layer.aws_cache_dir / "bb-account-devops").stat().st_mode & 0o777 == 0o600


def test_mfa_uses_cached_credentials_while_valid(mfa_layer, stubs, mfa_codes):
    _, asked = mfa_codes
    mfa_layer.aws_cache_dir.mkdir(parents=True)
    expiration = datetime.now(timezone.utc) + timedelta(hours=2)
    (mfa_layer.aws_cache_dir / "bb-account-devops").write_text(
        json.dumps({"Expiration": expiration.strftime("%Y-%m-%dT%H:%M:%SZ")})
    )

    refresh_layer_credentials_mfa(mfa_layer)

    assert asked == []


@pytest.mark.parametrize("keys_in", ["credentials", "config"])
def test_mfa_assumes_the_role_with_the_source_profile_of_the_project(mfa_layer, stubs, mfa_codes, monkeypatch, keys_in):
    """The source profile's keys come from the project's own files (~/.aws/<project>), not ~/.aws. The AWS CLI
    takes them from either file."""
    keys = {"aws_access_key_id": "AKIASOURCE", "aws_secret_access_key": "source-secret"}
    if keys_in == "credentials":
        write_ini(mfa_layer.aws_credentials_file, {"bb-management-oaar": keys})
    else:
        write_ini(mfa_layer.aws_config_file, {**MFA_PROFILES, "profile bb-management-oaar": keys})
    used_keys = []

    class Session(boto3.session.Session):
        def client(self, service, **kwargs):
            used_keys.append(self.get_credentials().access_key)
            return stubs["sts"].client

    monkeypatch.setattr(auth_module.boto3, "Session", Session)
    mfa_codes[0].append("123456")
    stub_assume_role(stubs["sts"])

    refresh_layer_credentials_mfa(mfa_layer)

    assert used_keys == ["AKIASOURCE"]


def test_mfa_skips_local_references_and_cached_profiles_and_goes_on(mfa_layer, stubs, mfa_codes, monkeypatch):
    # A list, not a set, so the local reference and the cached profile come first
    monkeypatch.setattr(
        auth_module,
        "get_profiles",
        lambda paths: ("bb-account-devops", ["${local.profile}", "${var.project}-shared-devops", "${var.profile}"]),
    )
    write_ini(
        mfa_layer.aws_config_file,
        {**MFA_PROFILES, "profile bb-shared-devops-mfa": MFA_PROFILES["profile bb-account-devops-mfa"]},
    )
    mfa_layer.aws_cache_dir.mkdir(parents=True)
    expiration = datetime.now(timezone.utc) + timedelta(hours=2)
    (mfa_layer.aws_cache_dir / "bb-shared-devops").write_text(
        json.dumps({"Expiration": expiration.strftime("%Y-%m-%dT%H:%M:%SZ")})
    )
    mfa_codes[0].append("123456")
    stub_assume_role(stubs["sts"])

    refresh_layer_credentials_mfa(mfa_layer)

    assert set(read_ini(mfa_layer.aws_credentials_file)) == {"bb-account-devops"}


def test_mfa_on_a_for_each_provider(paths, stubs, mfa_codes):
    """`profile = each.value.profile` is the layer's own profile too."""
    set_layer_profiles(paths, "each.value.profile")
    write_ini(paths.aws_config_file, MFA_PROFILES)
    mfa_codes[0].append("123456")
    stub_assume_role(stubs["sts"])

    refresh_layer_credentials_mfa(paths)

    assert set(read_ini(paths.aws_credentials_file)) == {"bb-account-devops"}


def test_mfa_renews_cached_credentials_about_to_expire(mfa_layer, stubs, mfa_codes):
    # Within the 30 minutes margin, so a long apply does not run out of credentials
    mfa_layer.aws_cache_dir.mkdir(parents=True)
    expiration = datetime.now(timezone.utc) + timedelta(minutes=10)
    (mfa_layer.aws_cache_dir / "bb-account-devops").write_text(
        json.dumps({"Expiration": expiration.strftime("%Y-%m-%dT%H:%M:%SZ")})
    )
    codes, asked = mfa_codes
    codes.append("123456")
    stub_assume_role(stubs["sts"])

    refresh_layer_credentials_mfa(mfa_layer)

    assert len(asked) == 1


def test_mfa_asks_again_after_a_code_too_short(mfa_layer, stubs, mfa_codes, caplog):
    # botocore rejects it before sending it, so STS answers once. The Stubber checks the parameters before botocore
    # validates them: the queued response has to accept any code.
    codes, asked = mfa_codes
    codes.extend(["12345", "123456"])
    stub_assume_role(stubs["sts"], token_code=ANY)

    refresh_layer_credentials_mfa(mfa_layer)

    assert len(asked) == 2
    assert "Invalid token length, it must be 6 digits long. Please try again." in caplog.messages


def test_mfa_reports_an_invalid_mfa_profile_at_once(paths, stubs, mfa_codes, monkeypatch):
    """botocore rejects a role_arn too short before sending it, the way it rejects a short code: no point asking
    again. A real client, not the Stubber, whose own parameter check runs first; nothing is sent."""
    set_layer_profiles(paths, "var.profile")
    write_ini(
        paths.aws_config_file,
        {"profile bb-account-devops-mfa": {**MFA_PROFILES["profile bb-account-devops-mfa"], "role_arn": "x"}},
    )
    sts = boto3.session.Session().client("sts", region_name=REGION)
    monkeypatch.setattr(auth_module.boto3, "Session", lambda **kwargs: SimpleNamespace(client=lambda service: sts))
    codes, asked = mfa_codes
    codes.append("123456")

    with pytest.raises(ExitError, match="(?s)Error assuming role: .*parameter RoleArn") as error:
        refresh_layer_credentials_mfa(paths)

    assert error.value.exit_code == 50
    assert len(asked) == 1


@pytest.mark.parametrize(
    "wrong_code, constraint",
    [
        ("1234567", "Member must have length less than or equal to 6"),
        ("12345a", "Member must satisfy regular expression pattern: [\\d]*"),
    ],
)
def test_mfa_asks_again_after_a_code_sts_rejects(mfa_layer, stubs, mfa_codes, caplog, wrong_code, constraint):
    codes, asked = mfa_codes
    codes.extend([wrong_code, "123456"])
    stubs["sts"].add_client_error(
        "assume_role",
        service_error_code="ValidationError",
        service_message=f"1 validation error detected: Value '{wrong_code}' at 'tokenCode' failed to satisfy "
        f"constraint: {constraint}",
        http_status_code=400,
        expected_params={**ASSUME_ROLE_PARAMS, "TokenCode": wrong_code},
    )
    stub_assume_role(stubs["sts"], token_code="123456")

    refresh_layer_credentials_mfa(mfa_layer)

    assert len(asked) == 2
    assert "Invalid token code, it must be 6 digits long. Please try again." in caplog.messages


def test_mfa_asks_again_after_an_invalid_code(mfa_layer, stubs, mfa_codes):
    codes, asked = mfa_codes
    codes.extend(["000000", "123456"])
    stub_assume_role_error(
        stubs["sts"], "AccessDenied", "MultiFactorAuthentication failed with invalid MFA one time pass code. "
    )
    stub_assume_role(stubs["sts"], token_code="123456")

    refresh_layer_credentials_mfa(mfa_layer)

    assert len(asked) == 2
    assert "bb-account-devops" in read_ini(mfa_layer.aws_credentials_file)


def test_mfa_gives_up_after_three_invalid_codes(mfa_layer, stubs, mfa_codes):
    codes, asked = mfa_codes
    codes.extend(["000000", "111111", "222222"])
    for _ in range(3):
        stub_assume_role_error(
            stubs["sts"], "AccessDenied", "MultiFactorAuthentication failed with invalid MFA one time pass code. "
        )

    with pytest.raises(ExitError, match="Failed to get credentials after 3 attempts") as error:
        refresh_layer_credentials_mfa(mfa_layer)

    assert error.value.exit_code == 60
    assert len(asked) == 3


@pytest.mark.parametrize("code", ["AccessDenied", "AccessDeniedException"])
def test_mfa_reports_a_role_the_user_cannot_assume(mfa_layer, stubs, mfa_codes, code):
    # What STS answers when the source identity may not assume the role: no point asking again
    codes, asked = mfa_codes
    codes.append("123456")
    stub_assume_role_error(
        stubs["sts"],
        code,
        f"User: arn:aws:iam::000000000000:user/john is not authorized to perform: sts:AssumeRole on resource: {ROLE_ARN}",
    )

    with pytest.raises(ExitError, match="User does not have permission to assume role") as error:
        refresh_layer_credentials_mfa(mfa_layer)

    assert error.value.exit_code == 40
    assert len(asked) == 1


@pytest.mark.parametrize(
    "code, message",
    [
        # the source profile's own session expired: another MFA code would not help
        ("ExpiredTokenException", "The security token included in the request is expired"),
        # a wrong role_arn in the config
        ("ValidationError", "1 validation error detected: Value 'x' at 'roleArn' failed to satisfy constraint"),
    ],
)
def test_mfa_reports_any_other_error_at_once(mfa_layer, stubs, mfa_codes, code, message):
    codes, asked = mfa_codes
    codes.append("123456")
    stub_assume_role_error(stubs["sts"], code, message)

    with pytest.raises(ExitError, match="Error assuming role") as error:
        refresh_layer_credentials_mfa(mfa_layer)

    assert error.value.exit_code == 50
    assert len(asked) == 1


def test_mfa_requires_the_mfa_profile(paths, stubs, mfa_codes):
    set_layer_profiles(paths, "var.profile")
    write_ini(paths.aws_config_file, {"profile bb-management-oaar": {"region": REGION}})

    with pytest.raises(
        ExitError, match="Credentials for profile bb-account-devops have not been properly configured"
    ) as error:
        refresh_layer_credentials_mfa(paths)

    assert error.value.exit_code == 40
