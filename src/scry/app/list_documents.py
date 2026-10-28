from dataclasses import dataclass

from scry.app.sync_index import SyncIndex
from scry.domain import DocumentId


@dataclass(frozen=True)
class DocumentSummary:
    id: DocumentId
    title: str
    tags: list[str]
    summary: str | None


class ListDocuments:
    """The notes as of the last completed sync."""

    def __init__(self, sync: SyncIndex) -> None:
        self._sync = sync

    def __call__(self, tag: str | None = None) -> list[DocumentSummary]:
        return [
            DocumentSummary(doc_id, meta.title, meta.tags, meta.summary)
            for doc_id, meta in sorted(self._sync.snapshot.notes.items())
            if tag is None or tag in meta.tags
        ]
