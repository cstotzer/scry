from typing import Protocol

from scry.domain import Chunk, Document, DocumentId, IndexStats, SearchHit, Vectors


class VectorIndex(Protocol):
    """Derived, rebuildable index of document chunks."""

    def indexed_hashes(self) -> dict[DocumentId, str]: ...
    def replace(self, doc: Document, chunks: list[Chunk], vectors: list[Vectors]) -> None: ...
    def remove(self, doc_id: DocumentId) -> None: ...
    def search(
        self,
        query: Vectors,
        top_k: int,
        tags: list[str] | None,
        doc_ids: list[DocumentId] | None = None,
    ) -> list[SearchHit]: ...
    def stats(self) -> IndexStats: ...
