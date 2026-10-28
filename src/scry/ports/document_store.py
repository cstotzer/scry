from typing import Protocol

from scry.domain import DocumentId


class DocumentStore(Protocol):
    """Source of truth: the Markdown notes of the vault. Read-only; Obsidian writes them."""

    def list_ids(self) -> list[DocumentId]: ...
    def read_raw(self, doc_id: DocumentId) -> str: ...
