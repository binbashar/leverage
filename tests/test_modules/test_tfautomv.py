from click.testing import CliRunner
from leverage.modules.tfautomv import run

HELP_TEXT = """Usage: run [OPTIONS] [ARGS]...

  Generate a move tf file for this layer.

Options:
  --help  Show this message and exit.
"""


def test_auto_mv_invoke():
    runner = CliRunner()
    result = runner.invoke(run, ["--help"])
    assert result.exit_code == 0
    assert result.output == HELP_TEXT
