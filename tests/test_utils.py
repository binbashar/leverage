from configparser import NoOptionError

import pytest
from configupdater import ConfigUpdater

from leverage._utils import get_option_value, key_finder, make_private_dir, make_private_file, write_private_file


def test_key_finder_real_scenario():
    data = {
        "provider": [
            {
                "aws": {"region": "${var.region}", "profile": "${var.profile}"},
            },
        ],
        "terraform": [
            {
                "required_version": ">= 1.2.7",
                "required_providers": [{"aws": "~> 4.10", "sops": {"source": "carlpett/sops", "version": "~> 0.7"}}],
                "backend": [{"s3": {"key": "apps-devstg/notifications/terraform.tfstate"}}],
            }
        ],
        "data": [
            {
                "terraform_remote_state": {
                    "keys": {
                        "backend": "s3",
                        "config": {
                            "region": "${var.region}",
                            "profile": "${var.profile}",
                            "bucket": "${var.bucket}",
                            "key": "${var.environment}/security-keys/terraform.tfstate",
                        },
                    }
                }
            },
            {
                "sops_file": {"secrets": {"source_file": "secrets.enc.yaml"}},
            },
        ],
    }
    found = key_finder(data, "profile")

    assert found == ["${var.profile}", "${var.profile}"]


def test_key_finder_simple_scenario():
    data = {
        "test1": {
            "a": {"profile": "1a"},
            "b": {"profile": "1b"},
        },
        "test2": {"profile": "2"},
        "test3": {"profile": "3"},
    }
    found = key_finder(data, "profile")

    assert found == ["1a", "1b", "2", "3"]


def test_key_finder_skip_non_dict_values_in_lists():
    data = {
        "test1": {
            "a": {"profile": "1a"},
            "b": {"wrong": ["1b", "1c", "1d"]},
        },
    }
    found = key_finder(data, "profile")

    assert found == ["1a"]


def test_key_finder_avoid_lookup():
    data = {
        "terraform_remote_state": {
            "shared-vpcs": {
                "for_each": "${local.shared-vpcs}",
                "backend": "s3",
                "config": {
                    "region": '${lookup(each.value,"region")}',
                    "profile": '${lookup(each.value,"profile")}',
                    "bucket": '${lookup(each.value,"bucket")}',
                    "key": '${lookup(each.value,"key")}',
                },
            }
        },
        "profile": "valid",
    }
    found = key_finder(data, "profile", avoid="lookup")

    assert found == ["valid"]


def _updater(text):
    updater = ConfigUpdater(allow_no_value=True)
    updater.read_string(text)
    return updater


def test_get_option_value():
    updater = _updater("[profile bb-sso]\nsso_region = us-east-1\n")

    assert get_option_value(updater, "profile bb-sso", "sso_region") == "us-east-1"


@pytest.mark.parametrize("text", ["[profile bb-sso]\n", "[profile bb-sso]\nsso_region\n"], ids=["missing", "no-value"])
def test_get_option_value_requires_a_value(text):
    with pytest.raises(NoOptionError):
        get_option_value(_updater(text), "profile bb-sso", "sso_region")


def _mode(path):
    return path.stat().st_mode & 0o777


def test_make_private_dir_creates_and_tightens(tmp_path):
    tmp_path.chmod(0o755)
    new_dir = tmp_path / "project" / "sso" / "cache"
    make_private_dir(new_dir)
    assert _mode(new_dir) == 0o700
    assert _mode(tmp_path / "project" / "sso") == 0o700
    assert _mode(tmp_path / "project") == 0o700
    assert _mode(tmp_path) == 0o755, "a parent that already existed is left as it was"

    existing = tmp_path / "existing"
    existing.mkdir(mode=0o755)
    existing.chmod(0o755)
    make_private_dir(existing)
    assert _mode(existing) == 0o700


def test_make_private_file_creates_and_tightens_without_touching_the_content(tmp_path):
    new_file = tmp_path / "credentials"
    make_private_file(new_file)
    assert _mode(new_file) == 0o600
    assert new_file.read_text() == ""

    existing = tmp_path / "token"
    existing.write_text("secret")
    existing.chmod(0o644)
    make_private_file(existing)
    assert _mode(existing) == 0o600
    assert existing.read_text() == "secret"


def test_write_private_file(tmp_path):
    token = tmp_path / "token"
    token.write_text("old")
    token.chmod(0o644)

    write_private_file(token, "new")

    assert _mode(token) == 0o600
    assert token.read_text() == "new"
