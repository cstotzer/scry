from scry.domain import DocumentId, SearchHit
from scry.ports import Embedder, VectorIndex


class Search:
    def __init__(self, embedder: Embedder, index: VectorIndex) -> None:
        self._embedder, self._index = embedder, index

    def __call__(
        self,
        query: str,
        top_k: int = 8,
        tags: list[str] | None = None,
        doc_ids: list[DocumentId] | None = None,
    ) -> list[SearchHit]:
        if not query.strip():
            return []
        vectors = self._embedder.embed_query(query)
        return self._index.search(vectors, top_k, tags or None, doc_ids or None)
