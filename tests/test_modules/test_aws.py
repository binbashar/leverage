"""
CLI tests for `leverage aws`: `configure sso`, `sso login`, `sso refresh`, `sso logout` and the
pass-through to the AWS CLI.

The commands run end to end through Click, with two fakes at the edges:

* AWS APIs: real boto3 `sso` and `sso-oidc` clients wrapped in `botocore.stub.Stubber`, which
  checks operation names, request parameters and response shapes against the service models, so a
  typo in a call or a misread response key fails the test (a bare MagicMock would accept both).
* AWS CLI: a real `aws` executable on a temporary PATH, so `Runner` spawns a subprocess as usual.
  It implements `configure get/set` on the file `AWS_CONFIG_FILE` points to, the way the AWS CLI
  does, and logs any other invocation.

HOME points to a temporary directory, so nothing reads or writes the real ~/.aws.
"""

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
import pytest
from botocore.stub import ANY, Stubber
from configupdater import ConfigUpdater

from leverage.leverage import leverage

# `leverage.modules` exports the `aws` click group under the module's own name
aws_module = importlib.import_module("leverage.modules.aws")

REGION = "us-east-1"
START_URL = "https://bb.awsapps.com/start"
ACCESS_TOKEN = "the-access-token"

FAKE_AWS_CLI = """#!{python}
import configparser, os, sys

args = sys.argv[1:]
profile = "default"
if "--profile" in args:
    index = args.index("--profile")
    profile = args[index + 1]
    del args[index : index + 2]
section = "default" if profile == "default" else f"profile {{profile}}"
config_file = os.environ["AWS_CONFIG_FILE"]
config = configparser.ConfigParser()
config.read(config_file)

if args[:2] == ["configure", "get"]:
    value = config.get(section, args[2], fallback=None)
    if value is None:
        sys.exit(1)
    print(value)
elif args[:2] == ["configure", "set"]:
    if not config.has_section(section):
        config.add_section(section)
    config.set(section, args[2], args[3])
    with open(config_file, "w") as f:
        config.write(f)
else:
    with open(os.environ["FAKE_AWS_LOG"], "a") as f:
        f.write(" ".join(sys.argv[1:]) + "\\n")
    sys.exit(int(os.environ.get("FAKE_AWS_EXIT_CODE", "0")))
"""

COMMON_TFVARS = f"""
project      = "bb"
project_long = "binbash"
region       = "{REGION}"
sso_region   = "{REGION}"
sso_start_url = "{START_URL}"
organization = {{
  accounts = {{
    account = {{ id = "111111111111" }}
  }}
}}
"""


# ###########################################################################
# FIXTURES
# ###########################################################################
@pytest.fixture
def home(tmp_path, monkeypatch):
    """Isolate HOME, and keep botocore away from any real AWS configuration."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for var in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    # Wide enough that rich does not wrap the messages the tests look for
    monkeypatch.setenv("COLUMNS", "500")
    return home


@pytest.fixture
def fake_aws_cli(tmp_path, monkeypatch):
    """Put a fake `aws` executable first on PATH. Returns the file it logs other calls to."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    aws = bin_dir / "aws"
    aws.write_text(FAKE_AWS_CLI.format(python=sys.executable))
    aws.chmod(0o755)
    log = tmp_path / "aws-cli.log"
    monkeypatch.setenv("PATH", f"{bin_dir}:{Path(sys.executable).parent}:/usr/bin:/bin")
    monkeypatch.setenv("FAKE_AWS_LOG", str(log))
    return log


@pytest.fixture
def project(leverage_project):
    (leverage_project / "config" / "common.tfvars").write_text(COMMON_TFVARS)
    return leverage_project


@pytest.fixture
def aws_dir(home):
    """The project's AWS directory, as the cli lays it out: ~/.aws/<project>."""
    return home / ".aws" / "bb"


@pytest.fixture
def stubs(monkeypatch):
    """Real `sso` and `sso-oidc` clients under a Stubber, returned by `boto3.client`."""
    clients = {service: boto3.session.Session().client(service, region_name=REGION) for service in ("sso", "sso-oidc")}
    stubbers = {service: Stubber(client) for service, client in clients.items()}

    def client(service, region_name=None, **kwargs):
        assert region_name == REGION, f"{service} client created for region {region_name}"
        return clients[service]

    monkeypatch.setattr(aws_module.boto3, "client", client)
    for stubber in stubbers.values():
        stubber.activate()
    yield stubbers
    for stubber in stubbers.values():
        stubber.assert_no_pending_responses()
        stubber.deactivate()


@pytest.fixture
def browser(monkeypatch):
    opened = []
    monkeypatch.setattr(aws_module.webbrowser, "open_new_tab", opened.append)
    return opened


@pytest.fixture
def sleeps(monkeypatch):
    slept = []
    monkeypatch.setattr(aws_module.time, "sleep", slept.append)
    return slept


@pytest.fixture
def cli(project, leverage_runner, home, fake_aws_cli, stubs, browser, sleeps):
    """Invoke `leverage <args>` from the security-base layer, or from `working_dir`.

    Always under the AWS stubs, the browser and sleep fakes: a call a test did not expect fails at
    once (the Stubber has no response queued for it), instead of reaching AWS, opening a browser
    tab or polling forever.
    """

    def invoke(*args, working_dir=None):
        with leverage_runner(project, working_dir) as runner:
            return runner.invoke(leverage, list(args))

    return invoke


def write_aws_config(aws_dir, sections):
    aws_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for section, values in sections.items():
        lines.append(f"[{section}]")
        lines.extend(f"{key} = {value}" for key, value in values.items())
    (aws_dir / "config").write_text("\n".join(lines) + "\n")


def read_ini(path):
    updater = ConfigUpdater()
    updater.read(path)
    return {section: {k: v.value for k, v in updater[section].items()} for section in updater.sections()}


def stub_device_login(sso_oidc, pending=(), succeeds=True, token_expires_in=28800):
    """Queue the sso-oidc calls of a device login. `pending` lists the error codes create_token
    returns first; then it returns a token, unless `succeeds` is false."""
    client_secret_expires_at = int((datetime.now(timezone.utc) + timedelta(days=90)).timestamp())
    sso_oidc.add_response(
        "register_client",
        {
            "clientId": "the-client-id",
            "clientSecret": "the-client-secret",
            "clientSecretExpiresAt": client_secret_expires_at,
        },
        {"clientName": ANY, "clientType": "public"},
    )
    sso_oidc.add_response(
        "start_device_authorization",
        {"deviceCode": "the-device-code", "userCode": "ABCD-EFGH", "expiresIn": 600, "interval": 5},
        {"clientId": "the-client-id", "clientSecret": "the-client-secret", "startUrl": START_URL},
    )
    create_token_params = {
        "grantType": "urn:ietf:params:oauth:grant-type:device_code",
        "deviceCode": "the-device-code",
        "clientId": "the-client-id",
        "clientSecret": "the-client-secret",
    }
    for error_code in pending:
        sso_oidc.add_client_error(
            "create_token", service_error_code=error_code, http_status_code=400, expected_params=create_token_params
        )
    if succeeds:
        sso_oidc.add_response(
            "create_token",
            {"accessToken": ACCESS_TOKEN, "tokenType": "Bearer", "expiresIn": token_expires_in},
            create_token_params,
        )
    return client_secret_expires_at


# ###########################################################################
# sso login
# ###########################################################################
def test_login_caches_the_token_after_the_user_authorizes(cli, aws_dir, stubs, browser, sleeps):
    write_aws_config(aws_dir, {"profile bb-sso": {"sso_region": REGION}})
    stub_device_login(stubs["sso-oidc"], pending=["AuthorizationPendingException"])

    before = datetime.now(timezone.utc).replace(microsecond=0)
    result = cli("aws", "sso", "login")

    assert result.exit_code == 0, result.output
    assert browser == [f"{START_URL}/#/device?user_code=ABCD-EFGH"]
    # Polled again after the interval the device authorization asked for
    assert sleeps == [5]

    token = json.loads((aws_dir / "sso" / "cache" / "token").read_text())
    assert token["accessToken"] == ACCESS_TOKEN
    assert token["startUrl"] == START_URL
    assert token["region"] == REGION
    assert token["clientId"] == "the-client-id"
    assert token["clientSecret"] == "the-client-secret"
    expires_at = datetime.strptime(token["expiresAt"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert before + timedelta(hours=8) <= expires_at <= datetime.now(timezone.utc) + timedelta(hours=8)


def test_login_backs_off_when_asked_to_slow_down(cli, aws_dir, stubs, browser, sleeps):
    write_aws_config(aws_dir, {"profile bb-sso": {"sso_region": REGION}})
    stub_device_login(
        stubs["sso-oidc"],
        pending=[
            "SlowDownException",
            "AuthorizationPendingException",
            "SlowDownException",
            "AuthorizationPendingException",
        ],
    )

    result = cli("aws", "sso", "login")

    assert result.exit_code == 0, result.output
    # RFC 8628 (3.5): each slow_down adds 5 seconds to that wait and to every later one
    assert sleeps == [10, 10, 15, 15]


def test_login_aborts_on_any_other_error(cli, aws_dir, stubs, browser, sleeps):
    write_aws_config(aws_dir, {"profile bb-sso": {"sso_region": REGION}})
    stub_device_login(stubs["sso-oidc"], pending=["AccessDeniedException"], succeeds=False)

    result = cli("aws", "sso", "login")

    assert result.exit_code == 1
    assert "Aborting login process" in result.output
    assert not (aws_dir / "sso" / "cache" / "token").exists()


def test_login_requires_a_configured_sso_profile(cli, aws_dir, stubs, browser):
    write_aws_config(aws_dir, {"default": {"region": REGION}})

    result = cli("aws", "sso", "login")

    assert result.exit_code == 1
    assert "Region configuration for bb-sso profile not found" in result.output
    assert browser == []


@pytest.mark.parametrize("args, refreshes", [([], []), (["--refresh-all"], [False])])
def test_login_refreshes_all_accounts_only_when_asked(
    cli, aws_dir, stubs, browser, sleeps, monkeypatch, args, refreshes
):
    write_aws_config(aws_dir, {"profile bb-sso": {"sso_region": REGION}})
    stub_device_login(stubs["sso-oidc"])
    calls = []
    monkeypatch.setattr(
        aws_module, "refresh_all_accounts_credentials", lambda paths, force_refresh: calls.append(force_refresh)
    )

    result = cli("aws", "sso", "login", *args)

    assert result.exit_code == 0, result.output
    assert calls == refreshes


# ###########################################################################
# sso refresh
# ###########################################################################
@pytest.mark.parametrize("args, force", [([], False), (["--force"], True)])
def test_refresh_refreshes_all_accounts(cli, monkeypatch, args, force):
    calls = []
    monkeypatch.setattr(
        aws_module, "refresh_all_accounts_credentials", lambda paths, force_refresh: calls.append(force_refresh)
    )

    result = cli("aws", "sso", "refresh", *args)

    assert result.exit_code == 0, result.output
    assert calls == [force]


# ###########################################################################
# sso logout
# ###########################################################################
def test_logout_revokes_the_token_and_wipes_credentials(cli, aws_dir, stubs):
    write_aws_config(
        aws_dir, {"profile bb-sso": {"sso_region": REGION}, "profile bb-sso-account": {"role_name": "DevOps"}}
    )
    cache = aws_dir / "sso" / "cache"
    cache.mkdir(parents=True)
    (cache / "token").write_text(json.dumps({"accessToken": ACCESS_TOKEN}))
    (cache / "test-sso-role").write_text("{}")
    (aws_dir / "credentials").write_text("[bb-account-devops]\naws_access_key_id = AKIAEXAMPLE\n")
    stubs["sso"].add_response("logout", {}, {"accessToken": ACCESS_TOKEN})

    result = cli("aws", "sso", "logout")

    assert result.exit_code == 0, result.output
    assert list(cache.iterdir()) == []
    assert not (aws_dir / "credentials").exists()
    # The profiles stay, so the next login does not need `configure sso` again
    assert set(read_ini(aws_dir / "config")) == {"profile bb-sso", "profile bb-sso-account"}


def test_logout_without_a_session_still_wipes_credentials(cli, aws_dir, stubs):
    # Never logged in, or the token was removed: no token and no SSO call (the Stubber rejects
    # any call it has no response queued for), but whatever credentials are left go away
    aws_dir.mkdir(parents=True)
    (aws_dir / "credentials").write_text("[bb-account-devops]\naws_access_key_id = AKIAEXAMPLE\n")

    result = cli("aws", "sso", "logout")

    assert result.exit_code == 0, result.output
    assert "No active AWS SSO session found" in result.output
    assert not (aws_dir / "credentials").exists()


def test_logout_twice_succeeds(cli, aws_dir, stubs):
    cache = aws_dir / "sso" / "cache"
    cache.mkdir(parents=True)
    (cache / "token").write_text(json.dumps({"accessToken": ACCESS_TOKEN}))
    stubs["sso"].add_response("logout", {}, {"accessToken": ACCESS_TOKEN})

    first = cli("aws", "sso", "logout")
    second = cli("aws", "sso", "logout")

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output


def test_logout_with_an_expired_token_still_wipes_credentials(cli, aws_dir, stubs):
    cache = aws_dir / "sso" / "cache"
    cache.mkdir(parents=True)
    (cache / "token").write_text(json.dumps({"accessToken": ACCESS_TOKEN}))
    (aws_dir / "credentials").write_text("[bb-account-devops]\naws_access_key_id = AKIAEXAMPLE\n")
    stubs["sso"].add_client_error(
        "logout",
        service_error_code="UnauthorizedException",
        http_status_code=401,
        expected_params={"accessToken": ACCESS_TOKEN},
    )

    result = cli("aws", "sso", "logout")

    assert result.exit_code == 0, result.output
    assert "Could not end the AWS SSO session" in result.output
    assert list(cache.iterdir()) == []
    assert not (aws_dir / "credentials").exists()


# ###########################################################################
# configure sso
# ###########################################################################
def stub_account_listing(sso, accounts):
    sso.add_response(
        "list_accounts",
        {"accountList": [{"accountId": id_, "accountName": name} for name, id_, _ in accounts]},
        {"accessToken": ACCESS_TOKEN},
    )
    for _, id_, role in accounts:
        sso.add_response(
            "list_account_roles",
            {"roleList": [{"roleName": role, "accountId": id_}]},
            {"accessToken": ACCESS_TOKEN, "accountId": id_, "maxResults": 1},
        )


def test_configure_sso_sets_up_the_profiles_and_logs_in(cli, aws_dir, stubs, browser, sleeps):
    stub_device_login(stubs["sso-oidc"])
    stub_account_listing(
        stubs["sso"],
        [("binbash-management", "000000000000", "Administrator"), ("binbash-account", "111111111111", "DevOps")],
    )

    result = cli("aws", "configure", "sso")

    assert result.exit_code == 0, result.output
    config = read_ini(aws_dir / "config")
    assert config["default"] == {"region": REGION, "output": "json"}
    assert config["profile bb-sso"] == {
        "sso_start_url": START_URL,
        "sso_region": REGION,
        "sso_account_id": "111111111111",
        "sso_role_name": "test-sso-role",
    }
    # One profile per account, named after the account without the long project name
    for name, account_id, role in (
        ("management", "000000000000", "Administrator"),
        ("account", "111111111111", "DevOps"),
    ):
        assert config[f"profile bb-sso-{name}"] == {
            "role_name": role,
            "account_id": account_id,
            "sso_region": REGION,
            "sso_start_url": START_URL,
        }
    assert (aws_dir / "sso" / "cache" / "token").exists()


def test_configure_sso_finds_accounts_under_organizational_units(cli, project, aws_dir, stubs, browser, sleeps):
    common = project / "config" / "common.tfvars"
    common.write_text(
        common.read_text().replace(
            'accounts = {\n    account = { id = "111111111111" }\n  }',
            'organizational_units = {\n    apps = {\n      accounts = {\n        account = { id = "222222222222" }\n      }\n    }\n  }',
        )
    )
    stub_device_login(stubs["sso-oidc"])
    stub_account_listing(stubs["sso"], [("binbash-account", "222222222222", "DevOps")])

    result = cli("aws", "configure", "sso")

    assert result.exit_code == 0, result.output
    assert read_ini(aws_dir / "config")["profile bb-sso"]["sso_account_id"] == "222222222222"


@pytest.mark.parametrize(
    "common_tfvars, account_tfvars, message",
    [
        (
            f'project = "bb"\nregion = "{REGION}"\n',
            None,
            "Missing configuration values for SSO in global config file",
        ),
        (
            None,
            'environment = "account"\n',
            "Missing SSO role in account config file",
        ),
        (
            COMMON_TFVARS.replace("account = {", "other = {"),
            None,
            "Missing account configuration for account in global config file",
        ),
        (
            COMMON_TFVARS.replace('project_long = "binbash"\n', ""),
            None,
            "Missing project_long in global config file",
        ),
    ],
    ids=["no-sso-settings", "no-sso-role", "account-not-in-organization", "no-project-long"],
)
def test_configure_sso_reports_missing_configuration(cli, project, browser, common_tfvars, account_tfvars, message):
    if common_tfvars is not None:
        (project / "config" / "common.tfvars").write_text(common_tfvars)
    if account_tfvars is not None:
        (project / "account" / "config" / "account.tfvars").write_text(account_tfvars)

    result = cli("aws", "configure", "sso")

    assert result.exit_code == 1
    assert message in result.output
    assert browser == []


def test_configure_sso_only_runs_in_a_layer(cli, project, browser):
    result = cli("aws", "configure", "sso", working_dir=project / "account")

    assert result.exit_code == 1
    assert "cannot run neither in the root of the project or in the root directory of an account" in result.output
    assert browser == []


# ###########################################################################
# pass-through
# ###########################################################################
@pytest.mark.parametrize("exit_code", [0, 3])
def test_other_commands_go_to_the_aws_cli(cli, fake_aws_cli, monkeypatch, exit_code):
    monkeypatch.setenv("FAKE_AWS_EXIT_CODE", str(exit_code))

    result = cli("aws", "sts", "get-caller-identity", "--output", "json")

    assert result.exit_code == exit_code
    assert fake_aws_cli.read_text() == "sts get-caller-identity --output json\n"
