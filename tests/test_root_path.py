import subprocess

import pytest
from click.testing import CliRunner

from leverage import leverage
from leverage._utils import ExitError

from leverage.path import get_root_path, NotARepositoryError


@pytest.fixture
def no_enclosing_repo(tmp_path, monkeypatch):
    """Keep git from finding a repository above tmp_path (e.g. when the tests run inside a checkout)."""
    # These point git at a repository directly, skipping the discovery the ceiling limits (e.g. inside a git hook)
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    return tmp_path


def git_init(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


@pytest.mark.parametrize("subdir", ["", "account/layer"], ids=["root", "subdirectory"])
def test_returns_the_repository_root(no_enclosing_repo, monkeypatch, subdir):
    repo = git_init(no_enclosing_repo / "project")
    cwd = repo / subdir
    cwd.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(cwd)

    # A just-initialized repository, without commits, has a root too
    assert get_root_path() == str(repo.resolve())


def test_handles_unusual_characters_in_the_path(no_enclosing_repo, monkeypatch):
    repo = git_init(no_enclosing_repo / "🚀 project with spaces")
    monkeypatch.chdir(repo)

    assert get_root_path() == str(repo.resolve())


def test_outside_of_a_repository(no_enclosing_repo, monkeypatch):
    monkeypatch.chdir(no_enclosing_repo)

    with pytest.raises(NotARepositoryError):
        get_root_path()


def test_without_git_installed(no_enclosing_repo, monkeypatch):
    monkeypatch.setenv("PATH", str(no_enclosing_repo))

    with pytest.raises(NotARepositoryError):
        get_root_path()


def fake_git(directory, script):
    """A `git` executable that runs the given shell script."""
    directory.mkdir(exist_ok=True)
    git = directory / "git"
    git.write_text(f"#!/bin/sh\n{script}\n")
    git.chmod(0o755)
    return directory


TRANSLATED_GIT = """
if [ "$LC_ALL" = C ]; then
  echo "fatal: not a git repository (or any of the parent directories): .git" >&2
else
  echo "fatal: no es un repositorio git (ni ninguno de los directorios superiores): .git" >&2
fi
exit 128
"""

DUBIOUS_OWNERSHIP_GIT = """
echo "fatal: detected dubious ownership in repository at '/work/project'" >&2
echo "To add an exception for this directory, call:" >&2
echo "	git config --global --add safe.directory /work/project" >&2
exit 128
"""


def test_outside_of_a_repository_with_git_in_another_language(no_enclosing_repo, monkeypatch):
    # git translates its messages: get_root_path asks for them in English (#229, #356)
    monkeypatch.setenv("PATH", str(fake_git(no_enclosing_repo / "bin", TRANSLATED_GIT)))

    with pytest.raises(NotARepositoryError):
        get_root_path()


def test_any_other_git_error_is_reported(no_enclosing_repo, monkeypatch):
    # e.g. a repository owned by another user (Docker volumes, WSL): git refuses to work there (#356)
    monkeypatch.setenv("PATH", str(fake_git(no_enclosing_repo / "bin", DUBIOUS_OWNERSHIP_GIT)))

    with pytest.raises(ExitError, match="dubious ownership") as error:
        get_root_path()

    assert "safe.directory /work/project" in error.value.message


@pytest.fixture
def cli(no_enclosing_repo, monkeypatch):
    # Wide enough that rich does not wrap the messages the tests look for
    monkeypatch.setenv("COLUMNS", "500")
    monkeypatch.chdir(no_enclosing_repo)
    return CliRunner()


# Commands that ask for the project paths before looking for their binary, so the test needs none installed
@pytest.mark.parametrize("args", [["tofu", "plan"], ["terraform", "version"], ["kubectl", "get", "pods"]])
def test_commands_that_need_a_project_fail_outside_of_one(cli, args):
    result = cli.invoke(leverage, args)

    assert result.exit_code == 1
    assert "Out of Leverage project context" in result.output


@pytest.mark.parametrize("args", [["--version"], ["tofu", "--help"], ["run", "--list-tasks"]])
def test_commands_that_work_anywhere(cli, args):
    result = cli.invoke(leverage, args)

    assert result.exit_code == 0, result.output


def test_a_git_error_is_reported_by_the_command(cli, no_enclosing_repo, monkeypatch):
    monkeypatch.setenv("PATH", str(fake_git(no_enclosing_repo / "bin", DUBIOUS_OWNERSHIP_GIT)))

    result = cli.invoke(leverage, ["tofu", "plan"])

    assert result.exit_code == 1
    assert "Unable to find the root of the git repository" in result.output
    assert "safe.directory /work/project" in result.output
