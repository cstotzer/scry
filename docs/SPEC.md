# Knowledge Base MCP Server — Project Spec

> **Status:** original v1 design. kb has since become a read-only indexer for an Obsidian vault: no editing in the web UI, lenient properties instead of the front-matter contract (§4), a file watcher, and a link graph. Docker deployment was dropped. Where this document disagrees with `CLAUDE.md`, `CLAUDE.md` is current.
>
> The project was later renamed from **kb** to **Scry**: the package is now `scry`, the commands are `scry` / `scry-server`, and settings use the `SCRY_` prefix. The names below are the original ones.

A personal, local-first knowledge base. Markdown files are the source of truth. They are indexed into an embedded Qdrant store and exposed to chat clients (mainly VS Code Chat) through an MCP server. A small web UI creates, edits and deletes documents.

## 1. Goals

- Serve hybrid (semantic + keyword) search over Markdown documents to MCP clients.
- Store, update and delete documents through a simple web UI.
- Replacing a document removes **all** content of its previous version from the index.
- Validate front matter on save and on ingest.
- Develop in a devcontainer and run as a single Docker container.

### Non-goals (v1)

- Multi-user, authentication, permissions
- Document history or version numbers (replace-only semantics)
- Rerankers, query rewriting, retrieval tuning
- File watcher (sync runs on startup, after UI writes, and on demand)

## 2. Tech stack

| Concern            | Choice                                                     |
|--------------------|------------------------------------------------------------|
| Language / tooling | Python 3.12, **uv** (project, lockfile, scripts)           |
| Web framework      | FastAPI                                                    |
| Front end          | **HTMX + Jinja2** templates, server-rendered, no build step |
| MCP                | Official `mcp` Python SDK (FastMCP), streamable HTTP transport |
| Vector store       | **Qdrant embedded** (`QdrantClient(path=...)`, local mode)  |
| Embeddings         | `fastembed`: multilingual dense model + `Qdrant/bm25` sparse |
| Front matter       | `python-frontmatter` + Pydantic models                      |
| Config             | `pydantic-settings` (env vars, prefix `KB_`)                |
| Quality            | ruff, pyright (or mypy), pytest, **import-linter**          |

## 3. Architecture (hexagonal)

```
                 inbound adapters                        outbound adapters
          ┌───────────────────────────┐          ┌─────────────────────────────┐
          │ MCP server  (/mcp)        │          │ FilesystemDocumentStore      │
          │ Web UI      (/)           │──▶ app ──▶│ QdrantEmbeddedIndex          │
          │ CLI         (kb sync)     │   core   │ FastEmbedEmbedder            │
          └───────────────────────────┘          └─────────────────────────────┘
```

### 3.1 Domain (`kb.domain`): pure Python, no I/O, no third-party imports except Pydantic

- `DocumentId`: normalized relative path, e.g. `ops/proxy-setup.md`. This is the document's identity.
- `FrontMatter` (Pydantic, `extra="forbid"`):
  - `title: str`, required, non-empty
  - `tags: list[str] = []`: lowercase slugs
  - `summary: str | None`: max 300 chars
- `Document`: `id`, `front_matter`, `body`, `content_hash` (sha256 of the raw file)
- `Chunk`: `doc_id`, `index`, `heading_path: list[str]`, `text`
- `SearchHit`: `doc_id`, `title`, `heading_path`, `text`, `score`
- `MarkdownChunker`: splits the body by headings (H1–H3). Sections longer than `max_chars` are split by paragraph. Each chunk's embedded text is prefixed with `title > heading path`.
- Errors: `FrontMatterInvalid(errors)`, `DocumentNotFound`

### 3.2 Ports (`kb.ports`): `typing.Protocol` interfaces

```python
class DocumentStore(Protocol):  # source of truth
    def list_ids(self) -> list[DocumentId]: ...
    def read(self, doc_id: DocumentId) -> Document: ...
    def write(self, doc: Document) -> None: ...
    def delete(self, doc_id: DocumentId) -> None: ...


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[Vectors]: ...  # dense + sparse
    def embed_query(self, text: str) -> Vectors: ...


class VectorIndex(Protocol):  # derived, rebuildable
    def indexed_hashes(self) -> dict[DocumentId, str]: ...
    def replace(self, doc: Document, chunks: list[Chunk], vectors: list[Vectors]) -> None: ...
    def remove(self, doc_id: DocumentId) -> None: ...
    def search(self, query: Vectors, top_k: int, tags: list[str] | None) -> list[SearchHit]: ...
```

### 3.3 Application (`kb.app`): use cases, depend only on domain + ports

- `SaveDocument(doc_id, raw_markdown)`: parse and validate front matter, write to the store, reindex that document.
- `DeleteDocument(doc_id)`: delete from the store and the index.
- `SyncIndex()`: reconcile store against index:
  - hash differs or document not indexed → `replace`
  - indexed but no longer in the store → `remove`
  - invalid front matter → skip and report
  - returns a `SyncReport(added, updated, removed, invalid[])`
- `Search(query, top_k=8, tags=None)`
- `GetDocument(doc_id)`, `ListDocuments(tag=None)`

### 3.4 Adapters (`kb.adapters`)

- **Inbound**
  - `mcp/`: FastMCP tools `search`, `get_document`, `list_documents`, `reindex`. Tool descriptions state what the knowledge base contains. Results include `doc_id` and heading path for citation.
  - `web/`: FastAPI routers + Jinja2/HTMX templates (see §5).
  - `cli/`: `kb sync`, `kb search "<query>"` (for debugging).
- **Outbound**
  - `filesystem/`: reads and writes `*.md` under `KB_DATA_DIR`. Writes are atomic (temp file + rename). Rejects paths escaping the data dir.
  - `qdrant/`: one collection with named vectors `dense` + sparse `bm25`. Payload: `doc_id`, `hash`, `title`, `tags`, `heading_path`, `text`. Payload index on `doc_id` and `tags`. Point ID = `uuid5(doc_id + chunk_index)`. `replace` = delete by `doc_id` filter, then upsert. Hybrid query = prefetch dense + sparse, fused with RRF.
  - `fastembed/`: model names from config. Models are cached in `KB_MODEL_CACHE`.

### 3.5 Composition root (`kb.bootstrap`)

- Builds settings, adapters and use cases explicitly. No DI framework.
- Creates **one** FastAPI app that mounts the MCP streamable-HTTP app at `/mcp` (its session manager runs in the FastAPI lifespan) and the web UI at `/`.
- Runs `SyncIndex()` on startup.

> **Constraint:** embedded Qdrant allows only one process to open the storage directory. The MCP server, web UI and sync therefore run in the same process, and all index writes go through a single lock. The CLI refuses to run while the server holds the storage (or talks to the server's HTTP API instead).

### 3.6 Enforced boundaries (import-linter)

- `kb.domain` imports nothing from `kb.*` except itself.
- `kb.app` may import `kb.domain` and `kb.ports` only.
- `kb.adapters.*` may not import each other.
- Only `kb.bootstrap` imports adapters.

## 4. Front-matter contract

```markdown
---
title: Proxy setup for corporate network
tags: [network, devcontainer]
summary: How to configure HTTP proxies for Docker and uv.
---
# Proxy setup
...
```

- Missing or invalid front matter → UI save is rejected with field-level errors. Ingest skips the file and lists it on the status page.
- Unknown keys are rejected (catches typos).

## 5. Web UI (HTMX)

| Route                    | Purpose                                                          |
|--------------------------|------------------------------------------------------------------|
| `GET /`                  | Document list (title, path, tags, last indexed), tag filter, search box |
| `GET /docs/new`          | Editor: path field + textarea pre-filled with a front-matter template |
| `GET /docs/{id}`         | Editor for an existing document, with rendered preview           |
| `POST /docs/{id}`        | Save → validate → write → reindex; validation errors shown inline via HTMX swap |
| `DELETE /docs/{id}`      | Delete with confirm                                              |
| `POST /preview`          | Render Markdown preview (HTMX, debounced)                        |
| `GET /status`            | Last `SyncReport`, invalid files, chunk/doc counts, "Resync" button |
| `GET /search?q=`         | Test page showing raw search hits and scores                     |

Minimal styling (e.g. Pico.css). HTMX and CSS are served from `static/`, with no CDN dependency at runtime.

## 6. Configuration

| Env var              | Default                                             |
|----------------------|-----------------------------------------------------|
| `KB_DATA_DIR`        | `/data/knowledge`                                   |
| `KB_INDEX_DIR`       | `/data/index`                                       |
| `KB_MODEL_CACHE`     | `/data/models`                                      |
| `KB_DENSE_MODEL`     | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| `KB_SPARSE_MODEL`    | `Qdrant/bm25`                                       |
| `KB_HOST` / `KB_PORT`| `0.0.0.0` / `8080`                                  |
| `KB_CHUNK_MAX_CHARS` | `1500`                                              |

## 7. Project layout

```
.
├─ .devcontainer/
│  ├─ devcontainer.json      # Python 3.12 base, uv, forwards 8080, runs `uv sync`
│  └─ Dockerfile
├─ .vscode/mcp.json          # { "servers": { "kb": { "type": "http", "url": "http://localhost:8080/mcp" } } }
├─ Dockerfile                # multi-stage uv build, non-root, VOLUME /data
├─ docker-compose.yml        # single service, ./data mounted to /data
├─ pyproject.toml            # uv project, [project.scripts] kb = "kb.adapters.cli:main"
├─ .importlinter
├─ src/kb/
│  ├─ domain/
│  ├─ ports/
│  ├─ app/
│  ├─ adapters/{mcp,web,cli,filesystem,qdrant,fastembed}/
│  └─ bootstrap.py
└─ tests/
   ├─ unit/                  # domain + use cases with in-memory fakes for all ports
   ├─ integration/           # real filesystem + embedded Qdrant (tmp dirs), fake embedder
   └─ e2e/                   # MCP client against running app; one smoke test with real models
```

## 8. Acceptance criteria

1. `docker compose up` serves the UI on `:8080` and the MCP endpoint on `:8080/mcp`. VS Code Chat lists and calls the four tools.
2. Opening the repo in the devcontainer and running `uv run kb-server` gives the same result.
3. Saving a document with invalid front matter is rejected with field-level errors, and nothing is written.
4. After editing a document so that a section is removed, searching for text from the removed section returns no hit from that document.
5. Deleting a file on disk and resyncing removes all of its chunks.
6. Restarting the container keeps documents and index. Deleting `KB_INDEX_DIR` and restarting rebuilds the index from the files.
7. Search finds exact terms (e.g. a hostname) and paraphrased German/English questions.
8. `uv run lint-imports`, `uv run ruff check`, `uv run pyright` and `uv run pytest` pass.

## 9. Open points / risks

- Verify that hybrid queries (sparse vectors + RRF fusion) are supported in Qdrant local mode for the pinned client version. Fallback: dense-only search plus a payload full-text filter.
- Qdrant local mode is intended for small collections. That fits a single-user knowledge base; for a larger corpus, switch the `qdrant` adapter to server mode (same port, config change only).
