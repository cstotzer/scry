# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

A personal, local-first search index for an **Obsidian vault**. The vault's Markdown notes are the source of truth and Scry never writes to them; Obsidian is the only editor. The notes are indexed into embedded Qdrant (hybrid dense + BM25 search) and served to chat clients through an MCP server, plus a read-only web UI for browsing, search and index status. A file watcher keeps the index current. [docs/SPEC.md](docs/SPEC.md) is the original design; where it disagrees with this file, this file is current.

## Commands

Python 3.12 managed with **uv**; package under `src/scry/`. Scry runs natively (the target is Windows); there is no Docker deployment, and the devcontainer is for development only.

```bash
uv sync
uv run scry-server [vault] [-p N]  # web UI on 127.0.0.1:8080, MCP at :8080/mcp
uv run scry sync                   # CLI; refuses to run (exit 2) while the server holds the index
uv run scry search "<query>" [-k 8] [-t tag]
uv run scry links <doc_id> [-q query] [-n 10]
uv run scry agent-template [-o FILE] [--force]  # needs no vault; template is packaged in scry/adapters/cli/

uv run pytest                    # default run excludes the `models` marker (no model downloads)
uv run pytest -m models          # smoke test with the real fastembed models (~250 MB, cached in $SCRY_MODEL_CACHE or ~/.cache/scry-models)
uv run pytest tests/unit/test_use_cases.py::test_sync_reconciles_store_and_index
uv run ruff check && uv run ruff format
uv run pyright                   # strict mode, covers src and tests
uv run lint-imports              # layer contracts in .importlinter
```

Settings (`scry/config.py`, env prefix `SCRY_`):
- `SCRY_VAULT_DIR` defaults to the current folder, which must then contain `.obsidian`. This lets users run `scry-server` (installed with `uv tool install`) in their vault root. `scry-server <folder>` overrides it, and an explicit folder needs no `.obsidian`.
- `SCRY_INDEX_DIR` defaults to `~/.scry/index/<vault name>-<hash of its path>` (`config.default_index_dir`), so each vault has its own index. `SCRY_MODEL_CACHE` defaults to `~/.scry/models`, shared by all vaults. The index must not be inside the vault.
- `SCRY_EXCLUDE` takes comma-separated globs relative to the vault; a folder name excludes everything below it.
- `SCRY_WATCH` switches the file watcher.
- `SCRY_RESYNC_INTERVAL` is in seconds; 0 turns off the periodic resync.
- `SCRY_HUB_DEGREE` and `SCRY_LINKS_LIMIT` tune link handling.
- **Vault config file:** `<vault>/.scry.toml` (`config.read_vault_config`) may set the keys in `VAULT_CONFIG_KEYS` (title, exclude, port, host, public_url, watch, resync_interval, hub_degree, links_limit). Unknown keys and broken TOML raise errors. It is merged in `_vault_defaults` once the vault is known, with the lowest priority (init arguments > `SCRY_*` > file). `exclude` is split by a field validator so it accepts a list or a comma-separated string from either source.
- `SCRY_TITLE` is shown as **Scry** | title in the web header and `<title>`. It reaches every template through a Jinja2Templates `context_processor` in `build_web_router`.
- `SCRY_SYSTEM_CERTS` (default on): both entry points call `bootstrap.use_system_certs`, which runs `truststore.inject_into_ssl()`, so httpx (huggingface_hub) and requests trust the OS certificate store. This is for corporate TLS inspection. `create_app` doesn't call it, so tests never touch global SSL.
- `bootstrap.load_settings` turns a `ValidationError` into one `scry: SCRY_<FIELD>: message` line on stderr and exits with code 2. Both entry points use it.
- `SCRY_PUBLIC_URL` is the base of the note links in MCP results, as the user's browser reaches the server (for example behind a reverse proxy). It defaults to `http://<host>:<port>`.

The devcontainer points `SCRY_VAULT_DIR` at `./data/knowledge`. Set `WATCHFILES_FORCE_POLLING=true` where file events don't arrive, such as network shares or a vault on a Windows drive seen from WSL.

## Architecture

The code is hexagonal, and the layers are enforced by import-linter:

- `scry.domain` is pure: models, errors, `MarkdownChunker`, the Obsidian syntax helpers (`obsidian.py`: links, inline tags, embedding cleanup), `LinkResolver` / `LinkGraph` (`links.py`) and `is_excluded` (`vault.py`). Its only third-party dependency is Pydantic.
- `scry.ports` holds only Protocols, plus `IndexUnavailable`.
- `scry.app` holds the use cases. It may import nothing but the domain and the ports.
- Adapters never import each other. Logic they share goes into the domain; for example, `is_excluded` is used by both the filesystem store and the watcher.
- `scry.bootstrap` is the only module that imports adapters.

Code lives in one module per class or concern, for example `scry/app/sync_index.py`, `scry/ports/vector_index.py` and `scry/adapters/qdrant/index.py`. Each `__init__.py` only re-exports its package's public names; keep new code out of them.

Use cases are bundled into `Services` (`scry/app/services.py`): `sync`, `search`, `get`, `links`, `list_documents` and `stats`. Inbound adapters (`web`, `mcp`, `cli`, `watcher`) receive `Services`; the watcher gets an `on_change` callback instead. The CLI gets an `open_services` factory injected instead of importing bootstrap, which is why the `scry` script points at `scry.bootstrap:cli_main`. The factory also loads the settings, so `agent-template` (handled before it is called) works without a vault. The template itself is `scry/adapters/cli/agent-template.agent.md`, read with `importlib.resources`; keep its tool descriptions in step with the MCP tools. `app.state.services` exposes the services to tests.

How the pieces work:
- **`DocumentStore` is read-only** (`list_ids` / `read_raw`). It skips dot folders (`.obsidian`, `.trash`) and `SCRY_EXCLUDE`, and decodes with `errors="replace"`, so one bad file never stops a sync.
- **`MarkdownParser` never rejects a note.** It is implemented in `scry.adapters.frontmatter` with PyYAML.
  - Properties are optional and unknown ones are ignored.
  - The title is `title:` or else the file name.
  - Tags come from the `tags` property (a list or a string) plus inline `#tags`. They are lowercased, and a nested tag also yields its parents: `a/b` gives `a` and `a/b`.
  - Broken YAML is reported in `Document.warnings`, shown as `SyncReport.warnings` on `/status`, and the note is still indexed.
- **The link graph lives in memory.** `SyncIndex` parses every note on each run anyway (to compare hashes), so it rebuilds `LinkResolver` + `LinkGraph` from all notes and publishes them as one immutable `VaultSnapshot`, replaced in a single assignment. Nothing about links is stored in Qdrant. Resolution follows Obsidian:
  - a path is tried relative to the note, then from the vault root, then as a partial path;
  - otherwise the file name is matched case-insensitively, and the shortest path wins;
  - attachments are never notes.
- **Following links is capped.** `GetLinks` returns at most `limit` outgoing links and backlinks. Without a query, non-hubs come first, then notes mentioned more often, then notes with fewer neighbours. With a query, the linked notes are ranked by `Search(..., doc_ids=...)`. Hubs (degree ≥ `SCRY_HUB_DEGREE`) always come last.
- **Sync triggers.** At startup, `create_app`'s lifespan starts the sync in the background, so the server answers right away from the existing index. It also starts the watcher (`watchfiles`, debounced) and the periodic resync. All of them call `SyncIndex.request()`, which coalesces: a request during a running sync causes exactly one more run.
- `Embedder` exposes `dense_dim`, so the index knows the vector size. If the size changes (a different dense model), the Qdrant collection is dropped and rebuilt.

- **Citation URLs and heading anchors.** MCP results carry a `url` to the note page, pointing at the hit's heading (`heading_path[-1]`). `scry/adapters/web/anchors.py` owns the URL scheme and `heading_slug`. Bootstrap injects `note_href` into `build_mcp` as `note_url`, because adapters don't import each other. The renderer (`web/render.py`) gives every heading an id from the same `heading_slug`, applied to the source after wikilink replacement, which yields the same slug as the raw heading. Repeated headings get `-1`, `-2`. A search hit's URL is built from the heading text, so for a repeated heading it points at the first one. `get_document` also returns `sections`, every heading with its exact anchor URL. These come from `web.render.note_sections`, which uses the same parse as `render_note`, so they always match the page; bootstrap injects them into `build_mcp` as `note_sections`. Wikilinks with `#heading` link to the anchor, `[[#Heading]]` links within the page, block references (`^id`) link to the note, and relative `.md` Markdown links are resolved with `LinkResolver` too.
- **Mermaid** is rendered in the browser. `web/static/mermaid.min.js` is vendored and pinned to 11.17.2, its license sits next to it, and nothing comes from a CDN. `note.html` loads it only when the rendered note contains `language-mermaid`. A small inline script turns those code blocks into `div.mermaid` and calls `mermaid.run()` with `securityLevel: "strict"`. The diagram source never goes through wikilink replacement, because `mask_code` skips fenced blocks.

Invariants:
- **Replace-only indexing:** `QdrantEmbeddedIndex.replace` deletes every point with the document's `doc_id`, then upserts. `SyncIndex` compares the sha256 of the raw file to the hash stored in the payload. This also catches changes made while the server was down.
- **Every document yields at least one chunk.** An empty body produces a chunk from the summary or title. Without that chunk, no hash would be stored and every sync would re-add the document.
- **Chunk `text` is the original Markdown; only `embed_text` is cleaned** (`clean_for_embedding`: wikilinks become their display text, embeds and `%%comments%%` are dropped, callout markers removed).
- **One process owns the index.** Qdrant local mode takes an exclusive file lock on `SCRY_INDEX_DIR`, so the web UI, MCP, the watcher and sync all run in one process. Syncs go through the `threading.Lock` created in `open_services`, and the adapter also has its own RLock, because the local client is not thread-safe.

## Library gotchas (mcp 2.x, qdrant-client local mode, watchfiles)

- mcp 2.x renamed `FastMCP` to `mcp.server.mcpserver.MCPServer`, and `mcp.Client(url_or_server)` is the high-level client.
- `bootstrap.create_app` **appends the MCP app's routes** to the FastAPI router, rather than using `app.mount("/mcp", ...)`. A mount would serve `/mcp/` and redirect `/mcp`, which MCP clients do not follow.
- `mcp.session_manager.run()` must wrap the FastAPI lifespan.
- MCP DNS-rebinding protection checks the Host and Origin headers (421 / 403). `bootstrap.create_app` always passes `transport_security(hosts)` from `scry.adapters.mcp`. It allows localhost plus `SCRY_ALLOWED_HOSTS` plus `SCRY_PUBLIC_URL`'s host, each with and without a port, because behind a proxy on the default port the Host header has no port and mcp's `name:*` wildcard needs one. `*` disables the check.
- Qdrant local mode supports prefetch + RRF fusion and `Modifier.IDF` for BM25, but ignores payload indexes. They are still created, with the warning suppressed, so that server mode works unchanged.
- Renaming or deleting a folder only reports the folder path, so the watcher's filter also lets suffix-less paths through. The periodic resync catches anything the watcher misses.
- In tests, the MCP e2e test runs uvicorn in a thread on a free port. Because the startup sync runs in the background, e2e tests call `tests.fakes.wait_for_sync(app.state.services)` first. `tests/fakes.py` has in-memory fakes for every port; `FakeEmbedder` uses hashed bag-of-words vectors, so keyword search behaves realistically.
