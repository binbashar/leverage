from pathlib import Path

import pytest

from leverage import path as lepath
from leverage.path import get_home_path
from leverage.path import get_working_path
from leverage.path import get_account_path
from leverage.path import get_build_script_path
from leverage.path import get_global_config_path
from leverage.path import get_account_config_path


def test_get_working_path():
    assert get_working_path() == Path.cwd().as_posix()


def test_get_home_path():
    assert get_home_path() == Path.home().as_posix()


def test_get_root_path(pytester):
    # Allow importing from leverage
    pytester.syspathinsert(Path().cwd().parent)
    # Make a git repository
    pytester.run("git", "init")
    # The test itself
    test_file = pytester.makepyfile(
        """
        import pytest
        from pathlib import Path

        from leverage.path import get_root_path

        def test_get_root_path():
            root_path = get_root_path()

            assert root_path == Path.cwd().as_posix()
        """
    )
    result = pytester.runpytest(test_file)
    assert result.ret == 0


def test_get_root_path_not_in_a_git_repository(pytester):
    # Allow importing from leverage
    pytester.syspathinsert(Path().cwd().parent)
    # The test itself
    test_file = pytester.makepyfile(
        """
        import pytest

        from leverage.path import get_root_path
        from leverage.path import NotARepositoryError

        def test_get_root_path():
            with pytest.raises(NotARepositoryError):
                get_root_path()
        """
    )
    result = pytester.runpytest(test_file)
    assert result.ret == 0


def test_get_account_path(monkeypatch, tmp_path):
    # Make a deep directory structure
    root_dir = leaf_dir = tmp_path
    leaf_dir = leaf_dir / "subdir" / "subdir" / "subdir" / "subdir"
    leaf_dir.mkdir(parents=True)

    monkeypatch.setattr(lepath, "get_root_path", lambda: root_dir)
    monkeypatch.setattr(lepath, "get_working_path", lambda: leaf_dir)

    account_path = get_account_path()
    assert account_path == (root_dir / "subdir").as_posix()


def test_get_global_config_path(monkeypatch):
    monkeypatch.setattr(lepath, "get_root_path", lambda: ".")

    assert get_global_config_path() == "./config"


def test_get_account_config_path(monkeypatch):
    monkeypatch.setattr(lepath, "get_account_path", lambda: "./account")

    assert get_account_config_path() == "./account/config"


@pytest.mark.parametrize("build_script_location", ["", "account", "account/config"])
def test_get_build_script_path(dir_structure, build_script_location):
    root_dir, _ = dir_structure

    build_script = root_dir / build_script_location / "build.py"
    build_script.touch()

    build_script_path = get_build_script_path()
    assert build_script_path == build_script.as_posix()


def test_get_build_script_path_no_build_script(dir_structure):
    assert get_build_script_path() is None
