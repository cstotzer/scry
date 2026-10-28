from collections.abc import Callable

import anyio.to_thread
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from scry.adapters.mcp.schemas import (
    DocumentContent,
    DocumentListing,
    LinkedNote,
    NoteLinksResult,
    ReindexResult,
    SearchResult,
)
from scry.app import Services
from scry.domain import DocumentId, LinkRef, ScryError

# Browser URL of a note, pointing at a heading when given.
type NoteUrl = Callable[[DocumentId, str | None], str]

INSTRUCTIONS = """\
Personal knowledge base: an Obsidian vault of linked Markdown notes, in German and English. \
Use `search` first; it combines semantic and keyword matching, so both paraphrased questions \
and exact terms such as hostnames work. Then call `get_document` for the full text. When a \
note links to details it does not contain, call `get_links` with the user's question as \
`query` and open the few most promising links (about 3), at most 2 hops from the search hit. \
Notes marked `hub` link to many others (indexes, daily notes); open them only when nothing \
more specific fits. Cite every note you use as a Markdown link to its `url`, which opens the \
note in the user's browser at the matching section, e.g. [Proxy setup > Docker](url)."""


async def _run[T](fn: Callable[[], T]) -> T:
    try:
        return await anyio.to_thread.run_sync(fn)
    except ScryError as exc:
        raise ToolError(str(exc)) from exc


def _linked(ref: LinkRef, note_url: NoteUrl) -> LinkedNote:
    return LinkedNote(
        doc_id=str(ref.doc_id),
        url=note_url(ref.doc_id, None),
        title=ref.title,
        summary=ref.summary,
        mentions=ref.mentions,
        hub=ref.hub,
    )


def build_mcp(services: Services, note_url: NoteUrl) -> MCPServer:
    mcp = MCPServer(name="scry", title="Scry", instructions=INSTRUCTIONS)

    @mcp.tool(
        description=(
            "Hybrid semantic + keyword search over the personal Markdown knowledge base. "
            "Returns matching sections with doc_id, title, heading path and text. "
            "Optionally restrict to documents having any of the given tags."
        )
    )
    async def search(  # pyright: ignore[reportUnusedFunction]
        query: str, top_k: int = 8, tags: list[str] | None = None
    ) -> list[SearchResult]:
        hits = await _run(lambda: services.search(query, max(1, min(top_k, 50)), tags))
        return [
            SearchResult(
                doc_id=str(h.doc_id),
                url=note_url(h.doc_id, h.heading_path[-1] if h.heading_path else None),
                title=h.title,
                heading_path=h.heading_path,
                text=h.text,
                score=h.score,
            )
            for h in hits
        ]

    @mcp.tool(description="Return the full Markdown body and metadata of one document by doc_id.")
    async def get_document(doc_id: str) -> DocumentContent:  # pyright: ignore[reportUnusedFunction]
        doc = await _run(lambda: services.get(DocumentId(doc_id)))
        graph = services.sync.snapshot.graph
        return DocumentContent(
            doc_id=str(doc.id),
            url=note_url(doc.id, None),
            title=doc.meta.title,
            tags=doc.meta.tags,
            aliases=doc.meta.aliases,
            summary=doc.meta.summary,
            body=doc.body,
            outgoing_links=len(graph.outgoing(doc.id)),
            backlinks=len(graph.backlinks(doc.id)),
        )

    @mcp.tool(
        description=(
            "Notes linked from a note (outgoing) and notes linking to it (backlinks), each list "
            "capped at `limit`. Pass the user's question as `query` so the most relevant linked "
            "notes come first. `hub` marks notes with very many links (indexes, daily notes); "
            "`truncated` means more links exist than were returned."
        )
    )
    async def get_links(  # pyright: ignore[reportUnusedFunction]
        doc_id: str, query: str | None = None, limit: int = 10
    ) -> NoteLinksResult:
        links = await _run(
            lambda: services.links(DocumentId(doc_id), query, max(1, min(limit, 50)))
        )
        return NoteLinksResult(
            outgoing=[_linked(r, note_url) for r in links.outgoing],
            backlinks=[_linked(r, note_url) for r in links.backlinks],
            total_outgoing=links.total_outgoing,
            total_backlinks=links.total_backlinks,
            truncated=links.truncated,
            unresolved=links.unresolved,
        )

    @mcp.tool(
        description="List the documents in the knowledge base (doc_id, title, tags, summary), "
        "optionally only those with the given tag."
    )
    async def list_documents(  # pyright: ignore[reportUnusedFunction]
        tag: str | None = None,
    ) -> list[DocumentListing]:
        docs = await _run(lambda: services.list_documents(tag))
        return [
            DocumentListing(
                doc_id=str(d.id),
                url=note_url(d.id, None),
                title=d.title,
                tags=d.tags,
                summary=d.summary,
            )
            for d in docs
        ]

    @mcp.tool(
        description="Re-scan the vault and update the search index. Changes are normally "
        "picked up automatically within seconds; use this only if a recent edit is missing."
    )
    async def reindex() -> ReindexResult:  # pyright: ignore[reportUnusedFunction]
        report = await _run(services.sync)
        return ReindexResult(
            added=[str(d) for d in report.added],
            updated=[str(d) for d in report.updated],
            removed=[str(d) for d in report.removed],
            warnings={w.doc_id: w.messages for w in report.warnings},
        )

    return mcp
