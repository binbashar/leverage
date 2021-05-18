from pathlib import Path

import pytest
import click

from leverage import path as lepath


_BUILD_SCRIPTS = Path("./tests/build_scripts/").resolve()
BUILD_SCRIPT = _BUILD_SCRIPTS / "simple_build.py"


@pytest.fixture
def dir_structure(monkeypatch, tmp_path):
    root_dir = tmp_path
    leaf_dir = tmp_path / "account" / "config"
    leaf_dir.mkdir(parents=True)

    monkeypatch.setattr(lepath, "get_root_path", lambda: root_dir)
    monkeypatch.setattr(lepath, "get_working_path", lambda: leaf_dir)

    return root_dir, leaf_dir


@pytest.fixture
def click_context(verbose=True):
    return lambda: click.Context(click.Command("leverage"), obj={"verbose": verbose})
