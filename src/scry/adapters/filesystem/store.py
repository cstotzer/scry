from pathlib import Path

from scry.domain import DocumentId, DocumentNotFound, InvalidDocumentId, is_excluded


class FilesystemDocumentStore:
    """Reads the *.md notes below the vault root. Never writes."""

    def __init__(self, vault_dir: Path, exclude: list[str] | None = None) -> None:
        self._root = vault_dir.resolve()
        if not self._root.is_dir():
            raise FileNotFoundError(f"vault directory not found: {vault_dir}")
        self._exclude = exclude or []

    def _path(self, doc_id: DocumentId) -> Path:
        path = (self._root / doc_id.value).resolve()
        if not path.is_relative_to(self._root) or path == self._root:
            raise InvalidDocumentId(f"path escapes the vault: {doc_id}")
        return path

    def list_ids(self) -> list[DocumentId]:
        ids: list[DocumentId] = []
        for path in self._root.rglob("*.md"):
            rel = path.relative_to(self._root).as_posix()
            if path.is_file() and not is_excluded(rel, self._exclude):
                ids.append(DocumentId(rel))
        return sorted(ids)

    def read_raw(self, doc_id: DocumentId) -> str:
        if is_excluded(doc_id.value, self._exclude):
            raise DocumentNotFound(str(doc_id))
        try:
            # Undecodable bytes must not stop a sync; the hash still covers the raw file.
            return self._path(doc_id).read_bytes().decode("utf-8", errors="replace")
        except (FileNotFoundError, IsADirectoryError, NotADirectoryError) as exc:
            raise DocumentNotFound(str(doc_id)) from exc
