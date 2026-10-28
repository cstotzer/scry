from collections import Counter

from scry.app.search import Search
from scry.app.sync_index import SyncIndex, VaultSnapshot
from scry.domain import DocumentId, DocumentNotFound, LinkRef, NoteLinks


class GetLinks:
    """Outgoing links and backlinks of a note, capped at `limit` each.

    Without a query, specific notes come first (see `LinkGraph.rank`). With a query, linked
    notes that match it come first. Hubs always come last.
    """

    def __init__(self, sync: SyncIndex, search: Search, limit: int) -> None:
        self._sync, self._search, self._limit = sync, search, limit

    def __call__(
        self, doc_id: DocumentId, query: str | None = None, limit: int | None = None
    ) -> NoteLinks:
        snap = self._sync.snapshot
        if doc_id not in snap.notes:
            raise DocumentNotFound(str(doc_id))
        graph = snap.graph
        limit = max(1, limit or self._limit)
        outgoing, backlinks = graph.outgoing(doc_id), graph.backlinks(doc_id)
        return NoteLinks(
            outgoing=self._top(snap, outgoing, query, limit),
            backlinks=self._top(snap, backlinks, query, limit),
            total_outgoing=len(outgoing),
            total_backlinks=len(backlinks),
            unresolved=graph.unresolved(doc_id),
        )

    def _top(
        self, snap: VaultSnapshot, linked: Counter[DocumentId], query: str | None, limit: int
    ) -> list[LinkRef]:
        graph = snap.graph
        order = graph.rank(linked)
        if query and query.strip() and order:
            hits = self._search(query, min(len(order) * 3, 200), doc_ids=order)
            relevant = list(dict.fromkeys(h.doc_id for h in hits))
            order = relevant + [d for d in order if d not in relevant]
            order.sort(key=graph.is_hub)  # stable: keeps the relevance order within each group
        return [
            LinkRef(
                doc_id=d,
                title=snap.notes[d].title,
                summary=snap.notes[d].summary,
                mentions=linked[d],
                degree=graph.degree(d),
                hub=graph.is_hub(d),
            )
            for d in order[:limit]
        ]
