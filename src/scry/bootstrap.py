"""Composition root: the only module that knows the concrete adapters."""

import argparse
import logging
import sys
import threading
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any, NoReturn

import anyio.to_thread
import uvicorn
from fastapi import FastAPI
from pydantic import ValidationError

from scry.adapters import cli
from scry.adapters.fastembed import FastEmbedEmbedder
from scry.adapters.filesystem import FilesystemDocumentStore
from scry.adapters.frontmatter import FrontMatterParser
from scry.adapters.mcp import build_mcp
from scry.adapters.qdrant import QdrantEmbeddedIndex
from scry.adapters.watcher import watch_vault
from scry.adapters.web import mount_web, note_href
from scry.app import GetDocument, GetLinks, Indexer, ListDocuments, Search, Services, SyncIndex
from scry.config import Settings
from scry.domain import MarkdownChunker
from scry.ports import Embedder

log = logging.getLogger("scry")


@contextmanager
def open_services(settings: Settings, embedder: Embedder | None = None) -> Generator[Services]:
    """Wire adapters and use cases. Holds the embedded index open until exit."""
    if embedder is None:
        embedder = FastEmbedEmbedder(
            settings.dense_model, settings.sparse_model, settings.model_cache
        )
    store = FilesystemDocumentStore(settings.vault_dir, settings.exclude)
    parser = FrontMatterParser()
    index = QdrantEmbeddedIndex(settings.index_dir, embedder.dense_dim)
    try:
        lock = threading.Lock()  # every index write goes through this lock
        indexer = Indexer(MarkdownChunker(settings.chunk_max_chars), embedder, index)
        sync = SyncIndex(store, parser, index, indexer, lock, settings.hub_degree)
        search = Search(embedder, index)
        yield Services(
            sync=sync,
            search=search,
            get=GetDocument(store, parser),
            links=GetLinks(sync, search, settings.links_limit),
            list_documents=ListDocuments(sync),
            stats=index.stats,
        )
    finally:
        index.close()


def create_app(settings: Settings | None = None, embedder: Embedder | None = None) -> FastAPI:
    settings = settings or Settings()  # pyright: ignore[reportCallIssue]
    services_cm = open_services(settings, embedder)
    services = services_cm.__enter__()  # closed again in the lifespan
    base_url = (settings.public_url or f"http://{settings.host}:{settings.port}").rstrip("/")
    mcp = build_mcp(services, lambda doc_id, heading: base_url + note_href(doc_id, heading))
    mcp_app = mcp.streamable_http_app(streamable_http_path="/mcp")

    async def sync() -> None:
        try:
            await anyio.to_thread.run_sync(services.sync.request)
        except Exception:  # a failed sync must not stop the watcher; the next one retries
            log.exception("sync failed")
            return
        if (report := services.sync.last_report) is not None:
            log.info(
                "sync: %d added, %d updated, %d removed, %d warnings",
                len(report.added),
                len(report.updated),
                len(report.removed),
                len(report.warnings),
            )

    async def resync_periodically() -> None:
        while True:
            await anyio.sleep(settings.resync_interval)
            await sync()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        try:
            async with anyio.create_task_group() as tasks:
                # Serve right away; search answers from the existing index while this runs.
                tasks.start_soon(sync)
                if settings.watch:
                    tasks.start_soon(watch_vault, settings.vault_dir, settings.exclude, sync)
                if settings.resync_interval > 0:
                    tasks.start_soon(resync_periodically)
                async with mcp.session_manager.run():
                    yield
                tasks.cancel_scope.cancel()
        finally:
            services_cm.__exit__(None, None, None)

    app = FastAPI(title="Scry", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.services = services
    # Add the MCP route itself (not a Mount) so the endpoint is exactly /mcp, without a redirect.
    app.router.routes.extend(mcp_app.routes)
    mount_web(app, services, settings.links_limit)
    return app


def _config_error(exc: ValidationError) -> NoReturn:
    for error in exc.errors():
        field = ".".join(map(str, error["loc"]))
        where = f"SCRY_{field.upper()}: " if field else ""
        print(f"scry: {where}{error['msg'].removeprefix('Value error, ')}", file=sys.stderr)
    sys.exit(2)


def load_settings(**overrides: Any) -> Settings:
    """Settings from the SCRY_* variables and `overrides`; a bad config ends the program."""
    try:
        return Settings(**overrides)
    except ValidationError as exc:
        _config_error(exc)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="scry-server", description="Serve an Obsidian vault: web UI and MCP endpoint."
    )
    parser.add_argument(
        "vault",
        nargs="?",
        type=Path,
        help="vault folder (default: SCRY_VAULT_DIR or the current folder)",
    )
    parser.add_argument("-p", "--port", type=int, help="port (default: SCRY_PORT or 8080)")
    args = parser.parse_args(argv)
    given = {"vault_dir": args.vault, "port": args.port}
    settings = load_settings(**{k: v for k, v in given.items() if v is not None})
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    log.info("vault %s, index %s", settings.vault_dir.resolve(), settings.index_dir)
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


def cli_main() -> None:
    settings = load_settings()
    sys.exit(cli.run(sys.argv[1:], lambda: open_services(settings)))
