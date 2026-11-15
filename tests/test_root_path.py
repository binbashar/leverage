import subprocess

import pytest

from leverage.path import get_root_path, NotARepositoryError


@pytest.fixture
def no_enclosing_repo(tmp_path, monkeypatch):
    """Keep git from finding a repository above tmp_path (e.g. when the tests run inside a checkout)."""
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
