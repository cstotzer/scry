from pathlib import Path

import pytest

from scry.adapters.filesystem import FilesystemDocumentStore
from scry.domain import DocumentId, DocumentNotFound, InvalidDocumentId


def write(root: Path, rel: str, text: str = "x") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())


def test_lists_notes_skipping_dot_folders_and_excludes(tmp_path: Path) -> None:
    for rel in [
        "ops/proxy.md",
        "top.md",
        "notes.txt",
        ".obsidian/x.md",
        ".trash/old.md",
        "Templates/Daily.md",
        "Archive/2020/a.md",
        "Archive/keep.txt",
    ]:
        write(tmp_path, rel)
    store = FilesystemDocumentStore(tmp_path, ["Templates", "Archive/**"])
    assert store.list_ids() == [DocumentId("ops/proxy.md"), DocumentId("top.md")]
    with pytest.raises(DocumentNotFound):
        store.read_raw(DocumentId("Templates/Daily.md"))


def test_reads_raw_bytes_and_survives_bad_encoding(tmp_path: Path) -> None:
    write(tmp_path, "a.md", "äöü\r\nline")
    (tmp_path / "b.md").write_bytes(b"caf\xe9")
    store = FilesystemDocumentStore(tmp_path)
    assert store.read_raw(DocumentId("a.md")) == "äöü\r\nline"
    assert store.read_raw(DocumentId("b.md")) == "caf�"
    with pytest.raises(DocumentNotFound):
        store.read_raw(DocumentId("missing.md"))


def test_requires_an_existing_vault(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        FilesystemDocumentStore(tmp_path / "nope")


def test_rejects_symlink_escaping_the_vault(tmp_path: Path) -> None:
    vault, outside = tmp_path / "vault", tmp_path / "outside"
    vault.mkdir()
    write(outside, "evil.md")
    (vault / "link").symlink_to(outside)
    with pytest.raises(InvalidDocumentId):
        FilesystemDocumentStore(vault).read_raw(DocumentId("link/evil.md"))
