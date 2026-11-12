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


def test_cli_on_notes_conflict_defaults_to_skip() -> None:
    """
    Test the CLI: --on-notes-conflict defaults to skip
    """
    runner = CliRunner()
    result = runner.invoke(primelunch, ["--help"])
    assert "--on-notes-conflict [append|prepend|replace|skip]" in result.output
    assert "[default: skip]" in result.output
