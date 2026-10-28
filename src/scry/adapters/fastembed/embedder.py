from pathlib import Path

from fastembed import SparseTextEmbedding, TextEmbedding

from scry.domain import SparseVector, Vectors


class FastEmbedEmbedder:
    """Dense + sparse (BM25) embeddings via fastembed. Models load on first use."""

    def __init__(self, dense_model: str, sparse_model: str, cache_dir: Path) -> None:
        self._dense_name, self._sparse_name = dense_model, sparse_model
        self._cache_dir = str(cache_dir)
        self._dense: TextEmbedding | None = None
        self._sparse: SparseTextEmbedding | None = None
        self.dense_dim = TextEmbedding.get_embedding_size(dense_model)

    def _models(self) -> tuple[TextEmbedding, SparseTextEmbedding]:
        if self._dense is None or self._sparse is None:
            self._dense = TextEmbedding(self._dense_name, cache_dir=self._cache_dir)
            self._sparse = SparseTextEmbedding(self._sparse_name, cache_dir=self._cache_dir)
        return self._dense, self._sparse

    def embed_documents(self, texts: list[str]) -> list[Vectors]:
        dense, sparse = self._models()
        return [
            Vectors(
                dense=[float(x) for x in d],
                sparse=SparseVector([int(i) for i in s.indices], [float(v) for v in s.values]),
            )
            for d, s in zip(dense.embed(texts), sparse.embed(texts), strict=True)
        ]

    def embed_query(self, text: str) -> Vectors:
        dense, sparse = self._models()
        d = next(iter(dense.query_embed(text)))
        s = next(iter(sparse.query_embed(text)))
        return Vectors(
            dense=[float(x) for x in d],
            sparse=SparseVector([int(i) for i in s.indices], [float(v) for v in s.values]),
        )
