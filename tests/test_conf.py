from unittest import mock

import pytest
from click.testing import CliRunner

from leverage import leverage
from leverage.conf import load

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
        (  # Env files present
            True,
            {
                "PROJECT": "foobar",
                "MFA_ENABLED": "true",
                "ENTRYPOINT": "/bin/run",
                "DEBUG": "true",
                "CONFIG_PATH": "/home/user/.config/",
            },
        ),
        (False, {}),  # No env files
    ],
)
def test_load_config(monkeypatch, click_context, tmp_path, write_files, expected_values):
    with click_context():
        root_dir = tmp_path
        account_dir = tmp_path / "account"
        account_dir.mkdir()

        monkeypatch.setattr("leverage.conf.get_root_path", lambda: root_dir.as_posix())
        monkeypatch.setattr("leverage.conf.get_working_path", lambda: account_dir.as_posix())

        if write_files:
            (root_dir / "build.env").write_text(ROOT_ENV_FILE)
            (account_dir / "build.env").write_text(ACC_ENV_FILE)

        loaded_values = load()

        assert dict(loaded_values) == expected_values


def test_version_validation():
    """
    Test that we get a warning if we are working with a version lower than the required by the project.
    """
    runner = CliRunner()
    with mock.patch("leverage.conf.load", return_value={"LEVERAGE_CLI_VERSION": "99.9.9"}):
        result = runner.invoke(leverage)

    assert "is lower than the required minimum (99.9.9)" in result.output
    assert result.exit_code == 0
