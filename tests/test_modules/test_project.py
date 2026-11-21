import copy
import subprocess
from importlib import import_module
from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner
from jinja2 import FileSystemLoader

from leverage import conf, leverage
from leverage import path as lepath
from leverage._utils import ExitError

from leverage.modules.project import PROJECT_STRUCTURE, create, validate_config

project_module = import_module("leverage.modules.project")

VALID_CONFIG = {
    "project_name": "test",
    "short_name": "ok",
    "primary_region": "us-east-1",
    "secondary_region": "us-west-2",
    "organization": {
        "accounts": [
            {"name": "management", "email": "aws+management@example.com"},
            {"name": "security", "email": "aws+security@example.com"},
            {"name": "shared", "email": "aws+shared@example.com"},
        ],
        "organizational_units": [
            {"name": "security", "policy": ["aws_organizations_policy.default"], "accounts": ["security"]},
            {"name": "shared", "policy": ["aws_organizations_policy.standard"], "accounts": ["shared"]},
        ],
    },
    "accounts": {
        "shared": {
            "networks": [
                {
                    "cidr_block": "172.20.0.0/20",
                    "availability_zones": ["a", "b"],
                    "private_subnets_cidr": "172.20.0.0/21",
                    "private_subnets": ["172.20.0.0/23", "172.20.2.0/23"],
                    "public_subnets_cidr": "172.20.8.0/21",
                    "public_subnets": ["172.20.8.0/23", "172.20.10.0/23"],
                }
            ]
        }
    },
}


def valid_config(**overrides):
    return {**copy.deepcopy(VALID_CONFIG), **overrides}


def test_project_commands_run_before_the_project_configuration_exists(tmp_path, monkeypatch):
    """
    Test that the project commands do not require an already configured project.

    `project init` creates the git repository, so from that point on the configuration loads fine
    but holds no project name yet. Building the paths there aborts `project create` with
    "Project name has not been set", on what is a perfectly legitimate invocation.
    """
    root = tmp_path / "new-project"
    root.mkdir()
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)

    monkeypatch.setattr(lepath, "get_root_path", lambda: root)
    monkeypatch.setattr(lepath, "get_working_path", lambda: root)
    monkeypatch.setattr(conf, "get_root_path", lambda: root)
    monkeypatch.setattr(conf, "get_working_path", lambda: root)
    monkeypatch.setattr(Path, "cwd", lambda: root)

    result = CliRunner().invoke(leverage, ["project", "create"])

    # The command is reached, and reports the missing configuration file on its own terms, rather
    # than the run being aborted earlier while building the project paths.
    assert "Project name has not been set" not in result.output
    assert "No configuration file found for the project" in result.output


@pytest.mark.parametrize(
    "project_name,short_name",
    [
        # different valid project names
        ("fine", "ok"),
        ("fine123", "ok"),
        ("123fine", "ok"),
        ("hyphens-are-allowed", "ok"),
        # different valid short project names
        ("fine", "foo"),
        ("fine", "full"),
    ],
)
def test_validate_config_happy_path(project_name, short_name):
    assert validate_config(valid_config(project_name=project_name, short_name=short_name))


@pytest.mark.parametrize(
    "invalid_name",
    [
        "with spaces",
        "underscores_not_allowed",
        "not-alph@-characters!",
        "loooooooooooooooooooooooooooooooooooooooooooooooooooooong",
    ],
)
def test_validate_config_project_name_errors(muted_click_context, invalid_name):
    with pytest.raises(ExitError, match="Project name is not valid"):
        validate_config({"project_name": invalid_name, "short_name": "ok"})


@pytest.mark.parametrize(
    "invalid_name",
    [
        "longerthan",
        "1",
        "@-!#",
        "",
        "UPPR",
    ],
)
def test_validate_config_short_project_name_errors(muted_click_context, invalid_name):
    with pytest.raises(ExitError, match="Project short name is not valid"):
        validate_config({"project_name": "test", "short_name": invalid_name})


def _set(path, value):
    """Return a mutator that sets `value` at the given path (keys and list indexes) of a config."""

    def mutate(config):
        target = config
        for step in path[:-1]:
            target = target[step]
        target[path[-1]] = value

    return mutate


def _delete(path):
    def mutate(config):
        target = config
        for step in path[:-1]:
            target = target[step]
        del target[path[-1]]

    return mutate


def _append_account(account):
    return lambda config: config["organization"]["accounts"].append(account)


@pytest.mark.parametrize(
    "mutate,error",
    [
        # organization accounts
        (_append_account({"name": "apps-devstg", "email": "a@example.com"}), "Unknown: apps-devstg"),
        (_delete(["organization", "accounts", 1]), "Missing: security"),
        (_append_account({"name": "shared", "email": "a@example.com"}), "Duplicated: shared"),
        (_delete(["organization", "accounts"]), "Missing: management, security, shared"),
        (_set(["tf_binary"], 123), "tf_binary"),
        (_set(["organization", "accounts"], "management"), "must be a list of accounts"),
        (_set(["organization", "accounts", 0, "email"], "<aws+management@example.com>"), "email for account"),
        (_delete(["organization", "accounts", 2, "email"]), "email for account"),
        # organizational units
        (_delete(["organization", "organizational_units"]), "Without unit: security, shared"),
        (_delete(["organization", "organizational_units", 1]), "Without unit: shared"),
        (
            _set(["organization", "organizational_units", 0, "accounts"], ["security", "shared"]),
            "In more than one unit: shared",
        ),
        (_set(["organization", "organizational_units", 0, "accounts"], ["apps-devstg"]), "unknown account"),
        (_set(["organization", "organizational_units", 0, "accounts"], ["management"]), "management account"),
        (_set(["organization", "organizational_units", 0, "name"], "has spaces"), "organizational unit name"),
        (_set(["organization", "organizational_units", 1, "name"], "security"), "Duplicated organizational units"),
        (_set(["organization", "organizational_units", 0, "policy"], []), "policy"),
        (_set(["organization", "organizational_units", 0, "policy"], ["default"]), "policy"),
        (_set(["organization", "organizational_units", 0, "policy"], "aws_organizations_policy.default"), "policy"),
        (
            _set(
                ["organization", "organizational_units", 0, "policy"],
                ["aws_organizations_policy.default", "aws_organizations_policy.standard"],
            ),
            "exactly one",
        ),
        # shared network
        (_set(["accounts", "management"], {"networks": []}), "Only the .*shared.* account"),
        (_delete(["accounts"]), "must define at least one network"),
        (_set(["accounts", "shared", "networks"], []), "must define at least one network"),
        (_delete(["accounts", "shared", "networks", 0, "public_subnets"]), "missing: public_subnets"),
        (_set(["accounts", "shared", "networks", 0, "availability_zones"], ["us-east-1a"]), "availability_zones"),
        (_set(["accounts", "shared", "networks", 0, "cidr_block"], "172.20.0.0/40"), "Invalid CIDR block"),
        (_set(["accounts", "shared", "networks", 0, "private_subnets"], ["nope"]), "Invalid CIDR block"),
    ],
)
def test_validate_config_structure_errors(muted_click_context, mutate, error):
    config = valid_config()
    mutate(config)

    with pytest.raises(ExitError, match=error):
        validate_config(config)


def test_render_project_template_renders_every_account_in_the_project_structure(tmp_path):
    """Accounts are rendered from PROJECT_STRUCTURE, not from the order or content of project.yaml."""
    config = valid_config()
    config["organization"]["accounts"].reverse()

    with mock.patch.object(project_module, "_render_templates"), mock.patch.object(
        project_module, "_render_account_templates"
    ) as mocked_render_account:
        project_module._render_project_template(config=config, source=tmp_path)

    rendered = [call.kwargs["account_name"] for call in mocked_render_account.call_args_list]
    assert rendered == list(PROJECT_STRUCTURE)


def test_create_with_extra_account_fails_before_touching_the_project(muted_click_context, tmp_path, monkeypatch):
    config = valid_config()
    config["organization"]["accounts"].append({"name": "apps-devstg", "email": "a@example.com"})
    monkeypatch.setattr(project_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(project_module, "load_project_config", lambda: config)

    with mock.patch.object(project_module, "_copy_project_template") as mocked_copy, mock.patch.object(
        project_module, "_render_project_template"
    ) as mocked_render:
        with pytest.raises(ExitError, match="Unknown: apps-devstg"):
            create.callback()

    mocked_copy.assert_not_called()
    mocked_render.assert_not_called()
    assert not (tmp_path / "config").exists()


def test_create_orders_accounts_like_the_project_structure(tmp_path, monkeypatch):
    config = valid_config()
    config["organization"]["accounts"].reverse()
    monkeypatch.setattr(project_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(project_module, "load_project_config", lambda: config)

    with mock.patch.object(project_module, "_copy_project_template"), mock.patch.object(
        project_module, "_render_project_template"
    ) as mocked_render, mock.patch.object(project_module, "TFRunner"):
        create.callback()

    rendered_config = mocked_render.call_args.kwargs["config"]
    assert [account["name"] for account in rendered_config["organization"]["accounts"]] == list(PROJECT_STRUCTURE)


def test_render_templates_writes_to_the_current_project_root(tmp_path, monkeypatch):
    """The default destination must be resolved when rendering, not frozen at import time, so it always
    follows PROJECT_ROOT (and never writes into whatever directory the module was imported from)."""
    templates_repo = tmp_path / "templates"
    source = templates_repo / "template"
    source.mkdir(parents=True)
    template_file = source / "build.env.template"
    template_file.write_text("PROJECT={{ short_name }}")

    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setattr(project_module, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(project_module, "TEMPLATES_REPO_DIR", templates_repo)
    monkeypatch.setattr(
        project_module, "JINJA_ENV", project_module.Environment(loader=FileSystemLoader(templates_repo.as_posix()))
    )

    project_module._render_templates([template_file], config={"short_name": "ok"}, source=source)

    assert (project_root / "build.env").read_text() == "PROJECT=ok"


@pytest.mark.parametrize(
    "config,expected",
    [
        ({"short_name": "ok"}, "TF_BINARY="),
        ({"short_name": "ok", "tf_binary": "~/bin/tofu"}, "TF_BINARY=~/bin/tofu"),
    ],
)
def test_render_templates_tf_binary(tmp_path, monkeypatch, config, expected):
    """`tf_binary` from project.yaml ends up as TF_BINARY in build.env, empty (look up in PATH) when not set."""
    templates_repo = tmp_path / "templates"
    source = templates_repo / "template"
    source.mkdir(parents=True)
    template_file = source / "build.env.template"
    template_file.write_text("TF_BINARY={{ tf_binary }}")

    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setattr(project_module, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(project_module, "TEMPLATES_REPO_DIR", templates_repo)
    monkeypatch.setattr(
        project_module, "JINJA_ENV", project_module.Environment(loader=FileSystemLoader(templates_repo.as_posix()))
    )

    project_module._render_templates([template_file], config=config, source=source)

    assert (project_root / "build.env").read_text() == expected
