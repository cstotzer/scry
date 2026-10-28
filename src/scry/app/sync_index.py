import threading
from dataclasses import dataclass

from scry.app.indexer import Indexer
from scry.domain import (
    DocumentId,
    DocumentNotFound,
    FileWarning,
    Link,
    LinkGraph,
    LinkResolver,
    NoteMeta,
    SyncReport,
)
from scry.ports import DocumentStore, MarkdownParser, VectorIndex


@dataclass(frozen=True)
class VaultSnapshot:
    """Metadata and link graph of every note, as of the last completed sync."""

    notes: dict[DocumentId, NoteMeta]
    resolver: LinkResolver
    graph: LinkGraph


class SyncIndex:
    def __init__(
        self,
        store: DocumentStore,
        parser: MarkdownParser,
        index: VectorIndex,
        indexer: Indexer,
        lock: threading.Lock,
        hub_degree: int,
    ) -> None:
        self._store, self._parser, self._index = store, parser, index
        self._indexer, self._lock, self._hub_degree = indexer, lock, hub_degree
        self._state = threading.Lock()
        self._requested = self._dirty = False
        self.last_report: SyncReport | None = None
        # Replaced as a whole after each sync, so readers never see a half-built graph.
        self.snapshot = VaultSnapshot({}, LinkResolver([]), LinkGraph.empty())

    @property
    def running(self) -> bool:
        return self._lock.locked()

    def request(self) -> None:
        """Sync now; if a requested sync is already running, run once more after it instead."""
        with self._state:
            if self._requested:
                self._dirty = True
                return
            self._requested = True
        try:
            while True:
                self()
                with self._state:
                    if not self._dirty:
                        return
                    self._dirty = False
        finally:
            with self._state:
                self._requested = self._dirty = False

    def __call__(self) -> SyncReport:
        report = SyncReport()
        notes: dict[DocumentId, NoteMeta] = {}
        links: dict[DocumentId, list[Link]] = {}
        with self._lock:
            indexed = self._index.indexed_hashes()
            for doc_id in sorted(self._store.list_ids()):
                try:
                    raw = self._store.read_raw(doc_id)
                except DocumentNotFound:
                    continue  # deleted while syncing; removed from the index below
                doc = self._parser.parse(doc_id, raw)
                notes[doc_id], links[doc_id] = doc.meta, doc.links
                if doc.warnings:
                    report.warnings.append(FileWarning(str(doc_id), doc.warnings))
                previous = indexed.get(doc_id)
                if previous == doc.content_hash:
                    continue
                self._indexer.index_document(doc)
                (report.added if previous is None else report.updated).append(doc_id)
            for doc_id in sorted(set(indexed) - set(notes)):
                self._index.remove(doc_id)
                report.removed.append(doc_id)
            resolver = LinkResolver(notes)
            graph = LinkGraph.build(links, resolver, self._hub_degree)
            self.snapshot = VaultSnapshot(notes, resolver, graph)
        self.last_report = report
        return report
