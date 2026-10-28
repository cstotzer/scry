from contextlib import AbstractContextManager
from pathlib import Path

import pytest

from scry.adapters.cli import run
from scry.adapters.cli.main import agent_template
from scry.app import Services
from scry.bootstrap import cli_main


def _no_vault() -> AbstractContextManager[Services]:
    raise AssertionError("agent-template must not open the vault or the index")


def test_agent_template_is_printed(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["agent-template"], _no_vault) == 0
    out = capsys.readouterr().out
    assert out == agent_template()
    assert out.startswith("---\n") and "{{AGENT_NAME}}" in out and "scry/search" in out


def test_agent_template_is_written_as_utf8(tmp_path: Path) -> None:
    target = tmp_path / ".github/agents/work.agent.md"
    assert run(["agent-template", "-o", str(target)], _no_vault) == 0
    assert target.read_bytes().decode("utf-8") == agent_template()
    assert "\u203a" in target.read_text(encoding="utf-8")  # link texts use a non-ASCII separator


def test_agent_template_does_not_overwrite_without_force(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "work.agent.md"
    target.write_text("mine")
    assert run(["agent-template", "-o", str(target)], _no_vault) == 1
    assert target.read_text() == "mine" and "--force" in capsys.readouterr().err
    assert run(["agent-template", "-o", str(target), "--force"], _no_vault) == 0
    assert target.read_text(encoding="utf-8") == agent_template()


def test_agent_template_works_outside_a_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SCRY_VAULT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)  # no .obsidian here
    monkeypatch.setattr("sys.argv", ["scry", "agent-template"])
    with pytest.raises(SystemExit) as exit_info:
        cli_main()
    assert exit_info.value.code == 0
    assert "{{AGENT_NAME}}" in capsys.readouterr().out
