"""
Example test case for lunchable-primelunch.
"""

from click.testing import CliRunner

from lunchable_primelunch.cli import primelunch


def test_cli_help() -> None:
    """
    Test the CLI: --help
    """
    runner = CliRunner()
    result = runner.invoke(primelunch, ["--help"])
    assert result.exit_code == 0
