import pytest

from leverage.conf import load
from leverage import conf as leconf


ROOT_ENV_FILE = """
# Project settings
PROJECT=foobar

# General
MFA_ENABLED=true
ENTRYPOINT=/bin/run
DEBUG=false
"""

ACC_ENV_FILE = """
# Environment settings
DEBUG=true
CONFIG_PATH=/home/user/.config/
"""


@pytest.mark.parametrize(
    "write_files, expected_values",
    [
        ( # Env files present
            True,
            {
                "PROJECT": "foobar",
                "MFA_ENABLED": "true",
                "ENTRYPOINT": "/bin/run",
                "DEBUG": "true",
                "CONFIG_PATH": "/home/user/.config/"
            }
        ),
        ( # No env files
            False,
            {}
        )
    ]
)
def test_load_config(monkeypatch, tmp_path, write_files, expected_values):
    root_dir = tmp_path
    account_dir = tmp_path / "account"
    account_dir.mkdir()

    monkeypatch.setattr(leconf, "get_root_path", lambda: root_dir)
    monkeypatch.setattr(leconf, "get_working_path", lambda: account_dir)

    if write_files:
        (root_dir / "build.env").write_text(ROOT_ENV_FILE)
        (account_dir / "build.env").write_text(ACC_ENV_FILE)

    loaded_values = load()

    assert loaded_values == expected_values
