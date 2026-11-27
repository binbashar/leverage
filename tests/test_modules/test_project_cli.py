"""
CLI tests for `leverage project init` and `leverage project create`, run on a snapshot of the real project
template (tests/project_template/, refreshed with tests/project_template/snapshot.py).

`project create`'s output is checked against golden files: the list of files it creates, and the files it renders
from templates, verbatim. The copied files must match the template. To regenerate the golden files after a change
that is meant to alter the output, run with UPDATE_GOLDEN=1 and review the diff.
"""

import os
import re
import shutil
import subprocess
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

import hcl2
import pytest
from click.testing import CliRunner
from jinja2 import Environment, FileSystemLoader

from leverage.leverage import leverage

project_module = import_module("leverage.modules.project")

TEMPLATE_SNAPSHOT = Path(__file__).parent.parent / "project_template" / "le-tf-infra-aws-template"
GOLDEN_DIR = Path(__file__).parent.parent / "project_template" / "golden"
UPDATE_GOLDEN = os.environ.get("UPDATE_GOLDEN") == "1"

PRIMARY_REGION = "us-east-1"
# What a user fills in project.yaml, as the ref-arch integration test does
PLACEHOLDERS = {
    "<project name>": "the-golden-project",
    "<short project name>": "gp",
    "<aws+management@example.com>": "aws+management@example.com",
    "<aws+security@example.com>": "aws+security@example.com",
    "<aws+shared@example.com>": "aws+shared@example.com",
    "<User>": "Jane",
    "<Name>": "Doe",
    "<user.name@example.com>": "jane.doe@example.com",
}


@pytest.fixture
def project_env(tmp_path, monkeypatch):
    """A home with no ~/.leverage yet and an empty project directory as cwd, the way a user starts.

    `git clone` of the template repository copies the snapshot instead; every other git command is real."""
    home = tmp_path / "home"
    home.mkdir()
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(project_root)

    leverage_dir = home / ".leverage"
    templates_repo_dir = leverage_dir / "templates"
    jinja_env = Environment(loader=FileSystemLoader(templates_repo_dir.as_posix()), trim_blocks=False)
    jinja_env.filters["value"] = project_module.value
    for name, value in {
        "LEVERAGE_DIR": leverage_dir,
        "TEMPLATES_REPO_DIR": templates_repo_dir,
        "TEMPLATE_DIR": templates_repo_dir / "template",
        "CONFIG_FILE_TEMPLATE": templates_repo_dir / "le-resources" / project_module.PROJECT_CONFIG_FILE,
        "PROJECT_ROOT": project_root,
        "PROJECT_CONFIG": project_root / project_module.PROJECT_CONFIG_FILE,
        "JINJA_ENV": jinja_env,
    }.items():
        monkeypatch.setattr(project_module, name, value)

    git_commands = []

    def git(command):
        git_commands.append(command)
        if command.startswith("clone "):
            destination = Path(command.split()[-1])
            shutil.copytree(TEMPLATE_SNAPSHOT, destination, symlinks=True, dirs_exist_ok=True)
            (destination / ".git").mkdir()
        elif not command.startswith("-C "):
            subprocess.run(["git", *command.split()], check=True, capture_output=True)

    monkeypatch.setattr(project_module, "git", git)

    return project_root, templates_repo_dir, git_commands


def _fill_project_yaml(project_root):
    project_yaml = project_root / "project.yaml"
    content = project_yaml.read_text()
    for placeholder, value in PLACEHOLDERS.items():
        content = content.replace(placeholder, value)
    assert not re.search(r"<[^>]*>", content), "project.yaml has placeholders the test doesn't fill"
    project_yaml.write_text(content)


def _create_project(project_root):
    """Run `project init`, fill project.yaml and run `project create`, without formatting (no tofu needed)."""
    runner = CliRunner()
    result = runner.invoke(leverage, ["project", "init"])
    assert result.exit_code == 0, result.output
    _fill_project_yaml(project_root)
    with patch.object(project_module, "TFRunner") as tf_runner:
        result = runner.invoke(leverage, ["project", "create"])
    assert result.exit_code == 0, result.output
    tf_runner.return_value.run.assert_called_with("fmt", "-recursive")
    return result


def _created_files(project_root):
    """Every file `project create` made, relative to the project, with symlinks shown as such."""
    files = {}
    for path in sorted(project_root.rglob("*")):
        relative = path.relative_to(project_root)
        if relative.parts[0] in (".git", "project.yaml") or (path.is_dir() and not path.is_symlink()):
            continue
        files[relative.as_posix()] = f"-> {os.readlink(path)}" if path.is_symlink() else ""
    return files


def _template_source(relative, templates_repo_dir):
    """The template file a created file comes from: the primary region directory is `primary_region` there."""
    parts = ["primary_region" if part == PRIMARY_REGION else part for part in Path(relative).parts]
    return templates_repo_dir / "template" / Path(*parts)


def test_init_sets_up_the_template_and_the_project(project_env):
    project_root, templates_repo_dir, git_commands = project_env

    result = CliRunner().invoke(leverage, ["project", "init"])

    assert result.exit_code == 0, result.output
    assert git_commands[0] == f"clone {project_module.LEVERAGE_TEMPLATE_REPO} {templates_repo_dir.as_posix()}"
    assert (project_root / ".git").is_dir()
    assert (project_root / "project.yaml").read_text() == (
        TEMPLATE_SNAPSHOT / "le-resources" / "project.yaml"
    ).read_text()


def test_init_again_updates_the_template_and_keeps_project_yaml(project_env):
    project_root, templates_repo_dir, git_commands = project_env
    runner = CliRunner()
    assert runner.invoke(leverage, ["project", "init"]).exit_code == 0
    (project_root / "project.yaml").write_text("project_name: mine\n")
    git_commands.clear()

    result = runner.invoke(leverage, ["project", "init"])

    assert result.exit_code == 0, result.output
    assert git_commands[:2] == [
        f"-C {templates_repo_dir.as_posix()} checkout master",
        f"-C {templates_repo_dir.as_posix()} pull",
    ]
    assert "already exists" in result.output
    assert (project_root / "project.yaml").read_text() == "project_name: mine\n"


def test_create_before_init_fails(project_env):
    result = CliRunner().invoke(leverage, ["project", "create"])

    assert result.exit_code == 1, result.output
    assert "No configuration file found" in result.output


def test_create_twice_fails_and_changes_nothing(project_env):
    project_root, _, _ = project_env
    _create_project(project_root)
    before = {path: (project_root / path).read_bytes() for path in _created_files(project_root)}

    result = CliRunner().invoke(leverage, ["project", "create"])

    assert result.exit_code == 1, result.output
    assert "already been created" in result.output
    assert {path: (project_root / path).read_bytes() for path in _created_files(project_root)} == before


def test_create_matches_the_golden_files(project_env):
    """The files `project create` makes from the template: which ones, and the content of the rendered ones."""
    project_root, templates_repo_dir, _ = project_env
    _create_project(project_root)
    files = _created_files(project_root)
    rendered = {path for path in files if not _template_source(path, templates_repo_dir).exists()}

    if UPDATE_GOLDEN:
        shutil.rmtree(GOLDEN_DIR, ignore_errors=True)
        (GOLDEN_DIR / "rendered").mkdir(parents=True)
        (GOLDEN_DIR / "files.txt").write_text("".join(f"{path} {link}".rstrip() + "\n" for path, link in files.items()))
        for path in rendered:
            (GOLDEN_DIR / "rendered" / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project_root / path, GOLDEN_DIR / "rendered" / path)

    golden_files = (GOLDEN_DIR / "files.txt").read_text().splitlines()
    assert [f"{path} {link}".rstrip() for path, link in files.items()] == golden_files
    golden_rendered = {
        path.relative_to(GOLDEN_DIR / "rendered").as_posix()
        for path in (GOLDEN_DIR / "rendered").rglob("*")
        if path.is_file()
    }
    assert rendered == golden_rendered
    for path in sorted(rendered):
        assert (project_root / path).read_text() == (GOLDEN_DIR / "rendered" / path).read_text(), path
    for path in sorted(set(files) - rendered):
        assert (project_root / path).read_bytes() == _template_source(path, templates_repo_dir).read_bytes(), path


def test_create_makes_parseable_hcl(project_env):
    """Every .tf and .tfvars file of the new project parses: a template that renders broken HCL fails here."""
    project_root, _, _ = project_env
    _create_project(project_root)

    hcl_files = [path for path in project_root.rglob("*") if path.suffix in (".tf", ".tfvars") and path.is_file()]

    assert hcl_files
    for path in hcl_files:
        try:
            hcl2.loads(path.read_text())
        except Exception as error:  # noqa: BLE001 - name the file whatever the parser raises
            pytest.fail(f"{path.relative_to(project_root)} doesn't parse: {error}")


def _layers(project_root):
    return sorted(
        path.parent.relative_to(project_root)
        for path in project_root.glob("*/*/*/config.tf")
        if path.parent.parts[-3] != "config"
    )


def test_every_created_layer_passes_validate_layout(project_env, leverage_runner):
    """Every layer `project create` makes passes validate-layout. The backend layers are the exception, by design:
    their backend block stays commented out until their first apply, and validate-layout says to skip validation."""
    project_root, _, _ = project_env
    _create_project(project_root)
    layers = _layers(project_root)
    assert len(layers) == sum(
        len(dirs["global"]) + len(dirs["primary_region"]) for dirs in project_module.PROJECT_STRUCTURE.values()
    )

    for layer in layers:
        with leverage_runner(project_root, working_directory=project_root / layer) as runner:
            result = runner.invoke(leverage, ["tofu", "validate-layout"])
        if layer.name == "base-tf-backend":
            assert result.exit_code == 1, f"{layer}:\n{result.output}"
            assert "--skip-validation" in result.output, f"{layer}:\n{result.output}"
        else:
            assert result.exit_code == 0, f"{layer}:\n{result.output}"
            assert "FAILED" not in result.output, f"{layer}:\n{result.output}"


def test_first_init_of_a_new_backend_layer(project_env, leverage_runner):
    """Regression test for #321: the new backend layer has its backend block commented out until its first apply,
    so its first init runs with --skip-validation, and it must reach tofu."""
    project_root, _, _ = project_env
    _create_project(project_root)
    layer = project_root / "management" / PRIMARY_REGION / "base-tf-backend"
    assert '# backend "s3"' in (layer / "config.tf").read_text()

    with leverage_runner(project_root, working_directory=layer) as runner:
        with patch("leverage.modules.tfrunner.TFRunner.run", return_value=0) as mocked_run:
            result = runner.invoke(leverage, ["tofu", "init", "--skip-validation"])

    assert result.exit_code == 0, result.output
    command, *args = mocked_run.call_args.args
    assert command == "init"
    assert f"-backend-config={project_root / 'management' / 'config' / 'backend.tfvars'}" in args
    assert mocked_run.call_args.kwargs["working_dir"] == layer


@pytest.mark.skipif(not shutil.which("tofu"), reason="needs tofu installed")
def test_create_formats_the_project(project_env):
    """With tofu installed, `project create` leaves the project formatted: `tofu fmt -check` finds nothing."""
    project_root, _, _ = project_env
    runner = CliRunner()
    assert runner.invoke(leverage, ["project", "init"]).exit_code == 0
    _fill_project_yaml(project_root)

    result = runner.invoke(leverage, ["project", "create"])

    assert result.exit_code == 0, result.output
    check = subprocess.run(["tofu", "fmt", "-check", "-recursive"], cwd=project_root, capture_output=True, text=True)
    assert check.returncode == 0, f"Not formatted:\n{check.stdout}{check.stderr}"
