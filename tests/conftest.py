import pytest

from leverage import path as lepath


@pytest.fixture
def dir_structure(monkeypatch, tmp_path):
    root_dir = tmp_path
    leaf_dir = tmp_path / "account" / "config"
    leaf_dir.mkdir(parents=True)

    monkeypatch.setattr(lepath, "get_root_path", lambda: root_dir)
    monkeypatch.setattr(lepath, "get_working_path", lambda: leaf_dir)

    return root_dir, leaf_dir
