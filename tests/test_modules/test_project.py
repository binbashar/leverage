import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from leverage import conf, leverage
from leverage import path as lepath
from leverage._utils import ExitError
from leverage.modules.project import validate_config


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
    assert validate_config({"project_name": project_name, "short_name": short_name})


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
