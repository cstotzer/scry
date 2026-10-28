from pathlib import Path

import anyio
import pytest
from watchfiles import Change

from scry.adapters.watcher import watch_vault
from scry.adapters.watcher.watch import note_filter


def test_filter_accepts_notes_and_folders_only(tmp_path: Path) -> None:
    accept = note_filter(tmp_path, ["Templates"])
    ok = [tmp_path / "a.md", tmp_path / "sub/B.MD", tmp_path / "renamed-folder"]
    no = [tmp_path / "img.png", tmp_path / ".obsidian/w.md", tmp_path / "Templates/t.md"]
    assert all(accept(Change.added, str(p)) for p in ok)
    assert not any(accept(Change.added, str(p)) for p in no)
    assert not accept(Change.added, str(tmp_path.parent / "outside.md"))


@pytest.mark.anyio
async def test_reports_note_changes(tmp_path: Path) -> None:
    calls: list[int] = []
    no_excludes: list[str] = []
    stop = anyio.Event()

    async def on_change() -> None:
        calls.append(1)
        stop.set()

    with anyio.fail_after(10):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(watch_vault, tmp_path, no_excludes, on_change, 50, stop)
            await anyio.sleep(0.3)  # let the watcher start
            (tmp_path / "attachment.png").write_bytes(b"x")
            (tmp_path / "note.md").write_text("hello")
    assert calls == [1]
