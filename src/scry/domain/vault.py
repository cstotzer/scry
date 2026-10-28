import fnmatch


def is_excluded(rel_path: str, exclude: list[str]) -> bool:
    """Dot folders (.obsidian, .trash, ...) and paths matching an exclude glob hold no notes.

    A pattern matches a path or, as a folder, anything below it: `Templates` excludes
    `Templates/Daily.md`.
    """
    if any(part.startswith(".") for part in rel_path.split("/")):
        return True
    return any(
        fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(rel_path, pattern.rstrip("/") + "/*")
        for pattern in exclude
    )
