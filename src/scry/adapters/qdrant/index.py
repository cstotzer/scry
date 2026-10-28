import threading
import uuid
import warnings
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient, models

from scry.domain import Chunk, Document, DocumentId, IndexStats, SearchHit, Vectors
from scry.ports import IndexUnavailable

COLLECTION = "kb_chunks"
DENSE = "dense"
SPARSE = "bm25"
_POINT_NAMESPACE = uuid.UUID("6f1c2a3e-5d4b-4c8a-9e7f-0a1b2c3d4e5f")


def _doc_filter(doc_id: DocumentId) -> models.Filter:
    return models.Filter(
        must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id.value))]
    )


def _sparse(v: Vectors) -> models.SparseVector:
    return models.SparseVector(indices=v.sparse.indices, values=v.sparse.values)


class QdrantEmbeddedIndex:
    """One collection with a named dense vector and a BM25 sparse vector, queried with RRF."""

    def __init__(self, path: Path, dense_dim: int) -> None:
        path.mkdir(parents=True, exist_ok=True)
        try:
            self._client = QdrantClient(path=str(path))
        except RuntimeError as exc:  # raised when another process holds the storage lock
            raise IndexUnavailable(str(exc)) from exc
        self._lock = threading.RLock()  # local mode is not safe for concurrent access
        self._ensure_collection(dense_dim)

    def _ensure_collection(self, dense_dim: int) -> None:
        if self._client.collection_exists(COLLECTION):
            info = self._client.get_collection(COLLECTION)
            vectors = info.config.params.vectors
            size = vectors[DENSE].size if isinstance(vectors, dict) and DENSE in vectors else None
            if size == dense_dim:
                return
            # The index is derived data: a model change means rebuilding it from the files.
            self._client.delete_collection(COLLECTION)
        self._client.create_collection(
            COLLECTION,
            vectors_config={
                DENSE: models.VectorParams(size=dense_dim, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        with warnings.catch_warnings():  # local mode ignores payload indexes; server mode uses them
            warnings.simplefilter("ignore", UserWarning)
            for field in ("doc_id", "tags"):
                self._client.create_payload_index(
                    COLLECTION, field, field_schema=models.PayloadSchemaType.KEYWORD
                )

    def close(self) -> None:
        with self._lock:
            self._client.close()

    def indexed_hashes(self) -> dict[DocumentId, str]:
        hashes: dict[DocumentId, str] = {}
        offset: Any = None
        with self._lock:
            while True:
                points, offset = self._client.scroll(
                    COLLECTION,
                    limit=512,
                    offset=offset,
                    with_payload=["doc_id", "hash"],
                    with_vectors=False,
                )
                for p in points:
                    payload = p.payload or {}
                    hashes[DocumentId(payload["doc_id"])] = payload["hash"]
                if offset is None:
                    return hashes

    def replace(self, doc: Document, chunks: list[Chunk], vectors: list[Vectors]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors differ in length")
        points = [
            models.PointStruct(
                id=str(uuid.uuid5(_POINT_NAMESPACE, f"{doc.id}#{chunk.index}")),
                vector={DENSE: vec.dense, SPARSE: _sparse(vec)},
                payload={
                    "doc_id": doc.id.value,
                    "hash": doc.content_hash,
                    "title": doc.meta.title,
                    "tags": doc.meta.tags,
                    "heading_path": chunk.heading_path,
                    "text": chunk.text,
                    "chunk_index": chunk.index,
                },
            )
            for chunk, vec in zip(chunks, vectors, strict=True)
        ]
        with self._lock:
            self._client.delete(
                COLLECTION, points_selector=models.FilterSelector(filter=_doc_filter(doc.id))
            )
            if points:
                self._client.upsert(COLLECTION, points=points)

    def remove(self, doc_id: DocumentId) -> None:
        with self._lock:
            self._client.delete(
                COLLECTION, points_selector=models.FilterSelector(filter=_doc_filter(doc_id))
            )

    def search(
        self,
        query: Vectors,
        top_k: int,
        tags: list[str] | None,
        doc_ids: list[DocumentId] | None = None,
    ) -> list[SearchHit]:
        must: list[models.Condition] = []
        if tags:
            must.append(models.FieldCondition(key="tags", match=models.MatchAny(any=tags)))
        if doc_ids:
            ids = [d.value for d in doc_ids]
            must.append(models.FieldCondition(key="doc_id", match=models.MatchAny(any=ids)))
        flt = models.Filter(must=must) if must else None
        candidates = max(top_k * 4, 20)
        prefetch = [models.Prefetch(query=query.dense, using=DENSE, limit=candidates, filter=flt)]
        if query.sparse.indices:  # a query of only stop words yields an empty sparse vector
            prefetch.append(
                models.Prefetch(query=_sparse(query), using=SPARSE, limit=candidates, filter=flt)
            )
        with self._lock:
            result = self._client.query_points(
                COLLECTION,
                prefetch=prefetch,
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                query_filter=flt,
                limit=top_k,
                with_payload=True,
            )
        hits: list[SearchHit] = []
        for p in result.points:
            payload = p.payload or {}
            hits.append(
                SearchHit(
                    doc_id=DocumentId(payload["doc_id"]),
                    title=payload["title"],
                    heading_path=list(payload["heading_path"]),
                    text=payload["text"],
                    score=p.score,
                )
            )
        return hits

    def stats(self) -> IndexStats:
        with self._lock:
            chunks = self._client.count(COLLECTION, exact=True).count
        return IndexStats(documents=len(self.indexed_hashes()), chunks=chunks)
