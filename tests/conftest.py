from pathlib import Path

import pytest
import click

from leverage import path as lepath
from leverage._internals import State
from leverage._internals import Module


BUILD_SCRIPTS = Path("./tests/build_scripts/").resolve()
BUILD_SCRIPT = BUILD_SCRIPTS / "simple_build.py"


@pytest.fixture
def dir_structure(monkeypatch, tmp_path):
    root_dir = tmp_path
    leaf_dir = tmp_path / "account" / "config"
    leaf_dir.mkdir(parents=True)

    monkeypatch.setattr(lepath, "get_root_path", lambda: root_dir)
    monkeypatch.setattr(lepath, "get_working_path", lambda: leaf_dir)

    return root_dir, leaf_dir


@pytest.fixture
def click_context():
    def context(verbose=True,
                build_script_name="build.py"):
        state = State()
        state.verbosity = verbose
        state.module = Module(name=build_script_name)

        return click.Context(command=click.Command("leverage"),
                             obj=state)

    return context


@pytest.fixture
def with_click_context(click_context):
    """ Utility fixture to use a default leverage click context without
    the need of a `with` statement. """
    with click_context():
        yield
