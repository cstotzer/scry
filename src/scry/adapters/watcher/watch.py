import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

import anyio
from watchfiles import Change, awatch  # pyright: ignore[reportUnknownVariableType]

from scry.domain import is_excluded

log = logging.getLogger("scry.watcher")


def note_filter(root: Path, exclude: list[str]) -> Callable[[Change, str], bool]:
    """Notes are *.md files outside dot folders and excluded paths. Paths without a suffix are
    let through too: renaming or deleting a folder only reports the folder itself."""
    root = root.resolve()

    def accept(_: Change, path: str) -> bool:
        p = Path(path)
        if p.suffix.lower() not in (".md", ""):
            return False
        try:
            rel = p.resolve().relative_to(root).as_posix()
        except ValueError:
            return False
        return not is_excluded(rel, exclude)

    return accept


async def watch_vault(
    root: Path,
    exclude: list[str],
    on_change: Callable[[], Awaitable[None]],
    debounce_ms: int = 1500,
    stop_event: anyio.Event | None = None,
) -> None:
    """Call `on_change` once per batch of note changes. Set WATCHFILES_FORCE_POLLING=true
    where file events do not arrive (network shares, some mounted volumes)."""
    log.info("watching %s", root)
    async for changes in awatch(
        root,
        watch_filter=note_filter(root, exclude),
        debounce=debounce_ms,
        stop_event=stop_event,
    ):
        log.info("%d note(s) changed, syncing", len(changes))
        await on_change()
