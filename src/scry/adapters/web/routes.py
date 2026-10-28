from html import escape
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from scry.adapters.web.anchors import note_href
from scry.adapters.web.render import render_note
from scry.app import Services
from scry.domain import DocumentId, DocumentNotFound, InvalidDocumentId

_HERE = Path(__file__).parent


def build_web_router(services: Services, links_limit: int, title: str | None = None) -> APIRouter:
    site = {"site_title": title}
    templates = Jinja2Templates(directory=_HERE / "templates", context_processors=[lambda _: site])
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    def index(request: Request, tag: str | None = None) -> Response:  # pyright: ignore[reportUnusedFunction]
        all_docs = services.list_documents()
        docs = all_docs if not tag else [d for d in all_docs if tag in d.tags]
        all_tags = sorted({t for d in all_docs for t in d.tags})
        return templates.TemplateResponse(
            request,
            "list.html",
            {"docs": docs, "tag": tag, "all_tags": all_tags, "syncing": services.sync.running},
        )

    @router.get("/notes/{doc_id:path}", response_class=HTMLResponse)
    def view_note(request: Request, doc_id: str) -> Response:  # pyright: ignore[reportUnusedFunction]
        try:
            parsed_id = DocumentId(doc_id)
            doc = services.get(parsed_id)
        except (InvalidDocumentId, DocumentNotFound) as exc:
            return HTMLResponse(f"<p>{escape(type(exc).__name__)}</p>", status_code=404)
        try:
            links = services.links(parsed_id, limit=links_limit)
        except DocumentNotFound:  # created after the last sync
            links = None
        html = render_note(parsed_id, doc.body, services.sync.snapshot.resolver)
        return templates.TemplateResponse(
            request,
            "note.html",
            # mermaid.js is 3.5 MB; load it only for notes with a diagram
            {"doc": doc, "html": html, "links": links, "mermaid": "language-mermaid" in html},
        )

    @router.get("/status", response_class=HTMLResponse)
    def status(request: Request) -> Response:  # pyright: ignore[reportUnusedFunction]
        return templates.TemplateResponse(
            request,
            "status.html",
            {
                "report": services.sync.last_report,
                "stats": services.stats(),
                "syncing": services.sync.running,
            },
        )

    @router.post("/status/resync")
    def resync() -> Response:  # pyright: ignore[reportUnusedFunction]
        services.sync.request()
        return RedirectResponse("/status", status_code=303)

    @router.get("/search", response_class=HTMLResponse)
    def search(request: Request, q: str = "", tags: str = "") -> Response:  # pyright: ignore[reportUnusedFunction]
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        hits = services.search(q, 20, tag_list or None) if q.strip() else []
        return templates.TemplateResponse(
            request, "search.html", {"q": q, "tags": tags, "hits": hits, "note_href": note_href}
        )

    return router


def mount_web(
    app: FastAPI, services: Services, links_limit: int = 10, title: str | None = None
) -> None:
    app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
    app.include_router(build_web_router(services, links_limit, title))
