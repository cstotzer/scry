import threading

import pytest

from scry.adapters.frontmatter import FrontMatterParser
from scry.app import GetDocument, GetLinks, Indexer, ListDocuments, Search, SyncIndex
from scry.domain import DocumentId, DocumentNotFound, MarkdownChunker, SyncReport
from tests.fakes import FakeEmbedder, InMemoryIndex, InMemoryStore, md

A = DocumentId("ops/proxy.md")


class World:
    def __init__(self, files: dict[str, str] | None = None, hub_degree: int = 30) -> None:
        self.store = InMemoryStore(files)
        self.index = InMemoryIndex()
        self.embedder = FakeEmbedder()
        parser = FrontMatterParser()
        indexer = Indexer(MarkdownChunker(200), self.embedder, self.index)
        self.sync = SyncIndex(self.store, parser, self.index, indexer, threading.Lock(), hub_degree)
        self.search = Search(self.embedder, self.index)
        self.get = GetDocument(self.store, parser)
        self.links = GetLinks(self.sync, self.search, limit=2)
        self.list = ListDocuments(self.sync)


def test_sync_reconciles_store_and_index() -> None:
    w = World({"a.md": md("A", "alpha"), "b.md": md("B", "beta"), "plain.md": "no properties"})
    first = w.sync()
    assert first.added == [DocumentId("a.md"), DocumentId("b.md"), DocumentId("plain.md")]
    assert first.warnings == []

    calls = w.embedder.calls
    assert w.sync().added == []  # unchanged hashes are skipped
    assert w.embedder.calls == calls

    w.store.put("a.md", md("A", "alpha changed"))
    w.store.remove("b.md")
    report = w.sync()
    assert report.updated == [DocumentId("a.md")]
    assert report.removed == [DocumentId("b.md")]
    assert w.index.chunk_texts(DocumentId("b.md")) == []
    assert w.sync.last_report == report


def test_replacing_a_note_removes_old_sections() -> None:
    w = World({"ops/proxy.md": md("Proxy", "# Docker\ndocker stuff\n# Legacy\nsquidhost.example")})
    w.sync()
    assert w.search("squidhost.example")
    w.store.put("ops/proxy.md", md("Proxy", "# Docker\ndocker stuff"))
    w.sync()
    assert w.index.chunk_texts(A) == ["docker stuff"]
    assert not w.search("squidhost.example")


def test_notes_with_broken_properties_are_indexed_with_a_warning() -> None:
    w = World({"a.md": "---\ntitle: [unclosed\n---\nalpha body"})
    report = w.sync()
    assert report.added == [DocumentId("a.md")]
    assert report.warnings[0].doc_id == "a.md"
    assert "invalid YAML" in report.warnings[0].messages[0]
    assert w.search("alpha")[0].title == "a"


def test_search_filters_by_tags_and_doc_ids_and_ignores_blank_query() -> None:
    w = World({"ops/proxy.md": "shared word #network", "b.md": "shared word #other"})
    w.sync()
    assert {h.doc_id for h in w.search("shared", tags=["network"])} == {A}
    assert {h.doc_id for h in w.search("shared", doc_ids=[A])} == {A}
    assert w.search("   ") == []


def test_list_and_get() -> None:
    w = World({"x/a.md": md("A", "alpha", ["t1"]), "b.md": "beta #t2"})
    assert w.list() == []  # nothing is known before the first sync
    w.sync()
    assert [(str(d.id), d.title, d.tags) for d in w.list()] == [
        ("b.md", "b", ["t2"]),
        ("x/a.md", "A", ["t1"]),
    ]
    assert [str(d.id) for d in w.list(tag="t1")] == ["x/a.md"]
    assert w.get(DocumentId("x/a.md")).body == "alpha"
    with pytest.raises(DocumentNotFound):
        w.get(DocumentId("missing.md"))


def test_renaming_a_target_updates_link_resolution() -> None:
    w = World({"a.md": "see [[Target]]", "Target.md": "t"})
    w.sync()
    assert [r.doc_id.value for r in w.links(DocumentId("a.md")).outgoing] == ["Target.md"]
    w.store.remove("Target.md")
    w.store.put("moved/Target.md", "t")
    w.sync()  # a.md itself is unchanged, its link still follows the note
    assert [r.doc_id.value for r in w.links(DocumentId("a.md")).outgoing] == ["moved/Target.md"]


def test_links_are_capped_and_ranked_by_query() -> None:
    w = World(
        {
            "src.md": "[[one]] [[two]] [[three]] [[three]]",
            "one.md": "cooking recipes",
            "two.md": "proxy configuration for docker",
            "three.md": "gardening",
            "back.md": "links to [[src]]",
        }
    )
    w.sync()
    src = DocumentId("src.md")
    plain = w.links(src)
    assert [r.doc_id.value for r in plain.outgoing] == ["three.md", "one.md"]
    assert plain.outgoing[0].mentions == 2
    assert (plain.total_outgoing, plain.truncated) == (3, True)
    assert [r.doc_id.value for r in plain.backlinks] == ["back.md"]

    ranked = w.links(src, query="docker proxy")
    assert ranked.outgoing[0].doc_id.value == "two.md"
    with pytest.raises(DocumentNotFound):
        w.links(DocumentId("missing.md"))


def test_hubs_come_last_even_when_they_match_the_query() -> None:
    w = World(
        {
            "src.md": "[[hub]] [[leaf]]",
            "hub.md": "docker [[x]] [[y]]",
            "leaf.md": "other",
            "x.md": "",
            "y.md": "",
        },
        hub_degree=3,
    )
    w.sync()
    refs = w.links(DocumentId("src.md"), query="docker").outgoing
    assert [(r.doc_id.value, r.hub) for r in refs] == [("leaf.md", False), ("hub.md", True)]


class SlowSync(SyncIndex):
    """Blocks inside the first sync until released."""

    def __init__(self, world: World) -> None:
        indexer = Indexer(MarkdownChunker(200), world.embedder, world.index)
        parser = FrontMatterParser()
        super().__init__(world.store, parser, world.index, indexer, threading.Lock(), 30)
        self.started, self.release = threading.Event(), threading.Event()
        self.runs = 0

    def __call__(self) -> SyncReport:
        self.runs += 1
        if self.runs == 1:
            self.started.set()
            self.release.wait(5)
        return super().__call__()


def test_request_coalesces_while_a_sync_runs() -> None:
    sync = SlowSync(World({"a.md": "alpha"}))
    first = threading.Thread(target=sync.request)
    first.start()
    assert sync.started.wait(5)
    for _ in range(5):
        sync.request()  # returns at once: only marks the running sync as dirty
    sync.release.set()
    first.join(5)
    assert sync.runs == 2
    assert not sync.running
