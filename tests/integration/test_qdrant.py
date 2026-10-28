from collections.abc import Generator
from pathlib import Path

import pytest

from scry.adapters.frontmatter import FrontMatterParser
from scry.adapters.qdrant import QdrantEmbeddedIndex
from scry.domain import DocumentId, MarkdownChunker
from scry.ports import IndexUnavailable
from tests.fakes import FakeEmbedder, md

EMBEDDER = FakeEmbedder()


@pytest.fixture
def index(tmp_path: Path) -> Generator[QdrantEmbeddedIndex]:
    idx = QdrantEmbeddedIndex(tmp_path / "index", EMBEDDER.dense_dim)
    yield idx
    idx.close()


def put(index: QdrantEmbeddedIndex, doc_id: str, raw: str) -> None:
    doc = FrontMatterParser().parse(DocumentId(doc_id), raw)
    chunks = MarkdownChunker(500).chunk(doc)
    index.replace(doc, chunks, EMBEDDER.embed_documents([c.embed_text for c in chunks]))


def test_replace_removes_previous_chunks(index: QdrantEmbeddedIndex) -> None:
    put(index, "a.md", md("A", "# One\nfirst unique-term-one\n# Two\nsecond unique-term-two"))
    assert index.stats().chunks == 2
    put(index, "a.md", md("A", "# One\nfirst unique-term-one"))
    assert index.stats().chunks == 1
    hits = index.search(EMBEDDER.embed_query("unique-term-two"), 5, None)
    assert all("unique-term-two" not in h.text for h in hits)


def test_hashes_remove_and_stats(index: QdrantEmbeddedIndex) -> None:
    put(index, "a.md", md("A", "alpha"))
    put(index, "sub/b.md", md("B", "beta"))
    assert set(index.indexed_hashes()) == {DocumentId("a.md"), DocumentId("sub/b.md")}
    index.remove(DocumentId("a.md"))
    assert set(index.indexed_hashes()) == {DocumentId("sub/b.md")}
    assert (index.stats().documents, index.stats().chunks) == (1, 1)


def test_hybrid_search_finds_exact_term_and_filters_tags(index: QdrantEmbeddedIndex) -> None:
    put(index, "proxy.md", md("Proxy", "# Host\nuse proxy01.corp.example:3128", ["network"]))
    put(index, "other.md", md("Other", "# Misc\nunrelated cooking notes", ["food"]))
    hits = index.search(EMBEDDER.embed_query("proxy01.corp.example"), 5, None)
    assert hits[0].doc_id == DocumentId("proxy.md")
    assert hits[0].heading_path == ["Host"]
    assert hits[0].title == "Proxy"
    tagged = index.search(EMBEDDER.embed_query("notes"), 5, ["network"])
    assert {h.doc_id for h in tagged} == {DocumentId("proxy.md")}
    only = index.search(EMBEDDER.embed_query("notes"), 5, None, [DocumentId("other.md")])
    assert {h.doc_id for h in only} == {DocumentId("other.md")}


def test_index_persists_and_rebuilds_on_dimension_change(tmp_path: Path) -> None:
    path = tmp_path / "index"
    idx = QdrantEmbeddedIndex(path, EMBEDDER.dense_dim)
    put(idx, "a.md", md("A", "alpha"))
    idx.close()
    idx = QdrantEmbeddedIndex(path, EMBEDDER.dense_dim)
    assert set(idx.indexed_hashes()) == {DocumentId("a.md")}
    idx.close()
    idx = QdrantEmbeddedIndex(path, EMBEDDER.dense_dim + 1)  # e.g. a different dense model
    assert idx.indexed_hashes() == {}
    idx.close()


def test_second_open_reports_index_unavailable(index: QdrantEmbeddedIndex, tmp_path: Path) -> None:
    with pytest.raises(IndexUnavailable):
        QdrantEmbeddedIndex(tmp_path / "index", EMBEDDER.dense_dim)
