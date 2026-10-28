"""In-memory fakes for every port, shared by unit, integration and e2e tests."""

import math
import re
import time
import zlib
from collections import Counter

from scry.domain import (
    Chunk,
    Document,
    DocumentId,
    DocumentNotFound,
    IndexStats,
    SearchHit,
    SparseVector,
    Vectors,
)

_TOKEN = re.compile(r"[\w.-]+")


def tokens(text: str) -> list[str]:
    return [t.lower().strip(".-") for t in _TOKEN.findall(text) if t.strip(".-")]


class FakeEmbedder:
    """Deterministic hashed bag-of-words embeddings: similar words give similar vectors."""

    dense_dim = 32

    def __init__(self) -> None:
        self.calls = 0

    def _embed(self, text: str) -> Vectors:
        counts = Counter(zlib.crc32(t.encode()) % 100_000 for t in tokens(text))
        dense = [0.0] * self.dense_dim
        for idx, n in counts.items():
            dense[idx % self.dense_dim] += n
        norm = math.sqrt(sum(x * x for x in dense)) or 1.0
        indices = sorted(counts)
        return Vectors(
            dense=[x / norm for x in dense],
            sparse=SparseVector(indices, [float(counts[i]) for i in indices]),
        )

    def embed_documents(self, texts: list[str]) -> list[Vectors]:
        self.calls += 1
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> Vectors:
        return self._embed(text)


class InMemoryStore:
    def __init__(self, files: dict[str, str] | None = None) -> None:
        self.files: dict[DocumentId, str] = {DocumentId(k): v for k, v in (files or {}).items()}

    def list_ids(self) -> list[DocumentId]:
        return sorted(self.files)

    def read_raw(self, doc_id: DocumentId) -> str:
        try:
            return self.files[doc_id]
        except KeyError as exc:
            raise DocumentNotFound(str(doc_id)) from exc

    def put(self, doc_id: str, raw: str) -> None:
        self.files[DocumentId(doc_id)] = raw

    def remove(self, doc_id: str) -> None:
        del self.files[DocumentId(doc_id)]


class InMemoryIndex:
    def __init__(self) -> None:
        self.entries: dict[DocumentId, tuple[Document, list[tuple[Chunk, Vectors]]]] = {}

    def indexed_hashes(self) -> dict[DocumentId, str]:
        return {doc_id: doc.content_hash for doc_id, (doc, _) in self.entries.items()}

    def replace(self, doc: Document, chunks: list[Chunk], vectors: list[Vectors]) -> None:
        self.entries[doc.id] = (doc, list(zip(chunks, vectors, strict=True)))

    def remove(self, doc_id: DocumentId) -> None:
        self.entries.pop(doc_id, None)

    def search(
        self,
        query: Vectors,
        top_k: int,
        tags: list[str] | None,
        doc_ids: list[DocumentId] | None = None,
    ) -> list[SearchHit]:
        wanted = dict(zip(query.sparse.indices, query.sparse.values, strict=True))
        hits: list[SearchHit] = []
        for doc, pairs in self.entries.values():
            if tags and not set(tags) & set(doc.meta.tags):
                continue
            if doc_ids and doc.id not in doc_ids:
                continue
            for chunk, vec in pairs:
                score = sum(
                    wanted.get(i, 0.0) * v
                    for i, v in zip(vec.sparse.indices, vec.sparse.values, strict=True)
                )
                if score > 0:
                    hits.append(
                        SearchHit(doc.id, doc.meta.title, chunk.heading_path, chunk.text, score)
                    )
        return sorted(hits, key=lambda h: -h.score)[:top_k]

    def stats(self) -> IndexStats:
        return IndexStats(len(self.entries), sum(len(p) for _, p in self.entries.values()))

    def chunk_texts(self, doc_id: DocumentId) -> list[str]:
        return [c.text for c, _ in self.entries[doc_id][1]] if doc_id in self.entries else []


def md(title: str, body: str, tags: list[str] | None = None) -> str:
    tag_list = ", ".join(tags or [])
    return f"---\ntitle: {title}\ntags: [{tag_list}]\n---\n{body}"


def wait_for_sync(services: object, timeout: float = 10) -> None:
    """Block until the background startup sync has completed."""
    from scry.app import Services

    assert isinstance(services, Services)
    deadline = time.monotonic() + timeout
    while services.sync.last_report is None or services.sync.running:
        if time.monotonic() > deadline:
            raise TimeoutError("sync did not finish")
        time.sleep(0.01)
