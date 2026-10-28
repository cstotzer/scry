from pathlib import Path

import pytest
import truststore

from scry.bootstrap import load_settings, use_system_certs
from scry.config import Settings, default_index_dir


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("SCRY_VAULT_DIR", "SCRY_INDEX_DIR", "SCRY_PORT", "SCRY_SYSTEM_CERTS"):
        monkeypatch.delenv(var, raising=False)


def test_the_current_folder_is_the_vault_when_it_is_an_obsidian_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".obsidian").mkdir()
    monkeypatch.chdir(tmp_path)
    settings = Settings()  # pyright: ignore[reportCallIssue]
    assert settings.vault_dir == tmp_path
    assert settings.index_dir == default_index_dir(tmp_path)


def test_any_other_folder_is_refused_with_a_readable_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exit_info:
        load_settings()
    assert exit_info.value.code == 2
    err = capsys.readouterr().err
    assert err.startswith("scry: ") and "not an Obsidian vault" in err
    assert "Traceback" not in err


def test_a_given_vault_needs_no_obsidian_folder_and_gets_its_own_index(tmp_path: Path) -> None:
    work, home = tmp_path / "Work", tmp_path / "Home"
    work.mkdir()
    home.mkdir()
    work_settings = Settings(vault_dir=work)  # pyright: ignore[reportCallIssue]
    home_settings = Settings(vault_dir=home)  # pyright: ignore[reportCallIssue]
    assert work_settings.index_dir != home_settings.index_dir
    assert work_settings.index_dir.name.startswith("Work-")
    assert work_settings.index_dir.parent == home_settings.index_dir.parent
    again = Settings(vault_dir=work)  # pyright: ignore[reportCallIssue]
    assert again.index_dir == work_settings.index_dir  # stable across runs


def test_explicit_settings_win(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCRY_VAULT_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("SCRY_INDEX_DIR", str(tmp_path / "index"))
    settings = load_settings(port=8099)
    assert settings.vault_dir == tmp_path / "vault"
    assert settings.index_dir == tmp_path / "index"
    assert settings.port == 8099


def test_bad_values_name_the_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SCRY_VAULT_DIR", str(tmp_path))
    monkeypatch.setenv("SCRY_PORT", "abc")
    with pytest.raises(SystemExit):
        load_settings()
    assert capsys.readouterr().err.startswith("scry: SCRY_PORT: ")


@pytest.mark.parametrize(("env", "injected"), [(None, True), ("false", False), ("true", True)])
def test_system_certs_are_used_unless_switched_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: str | None, injected: bool
) -> None:
    monkeypatch.setenv("SCRY_VAULT_DIR", str(tmp_path))
    if env is not None:
        monkeypatch.setenv("SCRY_SYSTEM_CERTS", env)
    calls: list[bool] = []
    monkeypatch.setattr(truststore, "inject_into_ssl", lambda: calls.append(True))
    use_system_certs(load_settings())
    assert calls == ([True] if injected else [])
