"""
Contract tests with the reference architecture (le-tf-infra-aws): the CLI must keep working on the project
layout and conventions the ref-arch uses.

By default they run on a snapshot of a few ref-arch layers, one per layout shape (tests/refarch/, refreshed with
tests/refarch/snapshot.py), so a CLI change that breaks the contract fails here, fast and without AWS. With
LEVERAGE_REFARCH_DIR pointing to a clone of le-tf-infra-aws they run on every layer of it instead, so a ref-arch
change that breaks the contract fails too (the `contract_tests_refarch` CI job).
"""

import os
import shutil
from pathlib import Path

import hcl2
import pytest
from configupdater import ConfigUpdater

from leverage import conf
from leverage._utils import ExitError
from leverage.leverage import leverage
from leverage.modules import auth
from leverage.modules.tf import _layer_backend_key, _make_layer_backend_key, tf_default_args
from leverage.path import PathsHandler

SNAPSHOT_DIR = Path(__file__).parent / "refarch" / "le-tf-infra-aws"
REFARCH_DIR = Path(os.environ.get("LEVERAGE_REFARCH_DIR") or SNAPSHOT_DIR).resolve()

# Profiles the ref-arch still uses that don't follow `<project>-<account>-<role>` with an existing account.
# The test for them is expected to fail (strict: once the ref-arch fixes them, remove them from here).
KNOWN_STALE_PROFILES = {
    # `root` was the old name of the management account: binbashar/le-tf-infra-aws#1347
    "network/us-east-1/client-vpn": "${var.project}-root-administrator",
}


def _is_disabled(name):
    """The ref-arch disables a layer by appending `--` to its directory name (sometimes followed by a space)."""
    return name.strip().endswith("--")


def _find_accounts(root):
    return sorted(path.parent.parent.relative_to(root) for path in root.glob("*/config/account.tfvars"))


def _find_layers(root):
    """Every enabled layer of every account: a directory below the account with a config.tf."""
    layers = []
    for account in _find_accounts(root):
        for config_tf in (root / account).rglob("config.tf"):
            layer = config_tf.parent.relative_to(root)
            if layer.parts[1] != "config" and not any(_is_disabled(part) for part in layer.parts):
                layers.append(layer)
    return sorted(layers)


ACCOUNTS = _find_accounts(REFARCH_DIR)
LAYERS = _find_layers(REFARCH_DIR)


@pytest.fixture(scope="module")
def refarch(tmp_path_factory):
    """A copy of the ref-arch to work on, with config/common.tfvars made from its example as the docs say."""
    root = tmp_path_factory.mktemp("refarch") / "le-tf-infra-aws"
    shutil.copytree(REFARCH_DIR, root, ignore=shutil.ignore_patterns(".git"), symlinks=True)
    common_tfvars = root / "config" / "common.tfvars"
    if not common_tfvars.exists():
        shutil.copyfile(root / "config" / "common.tfvars.example", common_tfvars)
    return root


@pytest.fixture
def paths_in(refarch, leverage_runner, click_context, monkeypatch, tmp_path):
    """Return the PathsHandler the CLI builds when run from the given directory of the ref-arch."""
    monkeypatch.setenv("HOME", str(tmp_path))

    def paths(directory):
        with leverage_runner(refarch, working_directory=refarch / directory), click_context():
            return PathsHandler(conf.load())

    return paths


def test_the_ref_arch_has_accounts_and_layers():
    """Guard: if the layout changes so much that nothing is found, the tests below would pass without checking."""
    assert ACCOUNTS
    assert len(LAYERS) >= len(ACCOUNTS)


@pytest.mark.parametrize("layer", LAYERS, ids=str)
def test_validate_layout_passes(refarch, leverage_runner, monkeypatch, tmp_path, layer):
    """Every ref-arch layer follows the conventions validate-layout checks: environment name, backend key and
    backend.tfvars names."""
    monkeypatch.setenv("HOME", str(tmp_path))

    with leverage_runner(refarch, working_directory=refarch / layer) as runner:
        result = runner.invoke(leverage, ["tofu", "validate-layout"])

    assert result.exit_code == 0, result.output
    assert "FAILED" not in result.output


@pytest.mark.parametrize("layer", LAYERS, ids=str)
def test_init_backend_key_is_accepted(refarch, layer):
    """The key init writes on a layer without one is a key validate-layout accepts for it."""
    account_dir = refarch / layer.parts[0]
    environment = hcl2.loads((account_dir / "config" / "account.tfvars").read_text())["environment"]

    expected_keys = _make_layer_backend_key(refarch / layer, account_dir, environment)

    assert _layer_backend_key(refarch / layer, refarch) in expected_keys


@pytest.mark.parametrize("layer", LAYERS, ids=str)
def test_layer_is_found_with_its_config(paths_in, layer):
    """From a layer, the CLI knows it is in a layer and passes the common and account tfvars to tofu."""
    paths = paths_in(layer)

    assert paths.get_location_type() == "layer"
    assert paths.project
    var_files = {Path(arg.removeprefix("-var-file=")).name for arg in tf_default_args.__wrapped__(paths)}
    assert {"common.tfvars", "account.tfvars", "backend.tfvars"} <= var_files


@pytest.mark.parametrize("account", ACCOUNTS, ids=str)
def test_account_directory(paths_in, account):
    """From an account directory the CLI knows where it is, and the account's environment name is its directory's."""
    paths = paths_in(account)

    assert paths.get_location_type() == "account"
    assert paths.account_conf["environment"] == account.name


def _profile_params():
    for layer in LAYERS:
        if layer.as_posix() in KNOWN_STALE_PROFILES:
            reason = f"stale profile {KNOWN_STALE_PROFILES[layer.as_posix()]} in the ref-arch"
            yield pytest.param(
                layer, id=str(layer), marks=pytest.mark.xfail(raises=ExitError, strict=True, reason=reason)
            )
        else:
            yield pytest.param(layer, id=str(layer))


@pytest.mark.parametrize("layer", list(_profile_params()))
def test_layer_profiles_resolve_to_accounts(paths_in, layer):
    """Each AWS profile a layer uses resolves to a project account, the way the SSO credential refresh does it.

    The sso profiles are the ones `leverage aws configure sso` writes, one per account of the project (the
    `accounts` in common.tfvars)."""
    paths = paths_in(layer)
    config = ConfigUpdater()
    for account_name in paths.common_conf["accounts"]:
        section = f"profile {paths.project}-sso-{account_name}"
        config.add_section(section)
        config[section]["account_id"] = "123456789012"
        config[section]["role_name"] = "DevOps"

    tf_profile, raw_profiles = auth.get_profiles(paths)

    assert tf_profile.startswith(f"{paths.project}-")
    for raw_profile in raw_profiles:
        try:
            auth.get_layer_profile(raw_profile, config, tf_profile, paths.project)
        except auth.SkipProfile:
            pass
