# Scry

**Look into your Obsidian vault, and let your agents look too.**

Scry indexes the notes in an [Obsidian](https://obsidian.md) vault for hybrid semantic and keyword search. It serves the index to AI agents over [MCP](https://modelcontextprotocol.io) and to you through a small read-only web UI. Every result carries a link to the exact section it came from, so when an agent cites your notes, you can click through and check them. Scry runs locally, never changes a note, and keeps its index current while you write.

## Obsidian and Scry

Obsidian is what lava becomes when it cools too fast to crystallise: a black volcanic glass that breaks into edges sharper than steel and polishes into a deep, dark mirror. The Aztecs used such mirrors to look for what the eye alone could not see. Their god Tezcatlipoca, the "smoking mirror", carried one. After the conquest, one of these mirrors travelled to England, where it became linked to John Dee, Elizabeth I's astrologer and a man who spent his life trying to see further. It still sits in the British Museum. The practice has a name: gazing into a dark surface until something surfaces is called *scrying*.

Your vault is the same kind of mirror. Over the years it fills with how-tos, setups and half-remembered fixes, all written and linked in Obsidian, and most of it sinks out of sight. Obsidian is where you shape that glass, and it stays the only place you do: the Markdown files are the truth, and nothing else edits them.

Scry is the looking. It reads the vault without leaving a mark, so it never writes, renames or deletes a note, and it treats your notes the way Obsidian does: it resolves wikilinks by the same rules, reads tags and properties, and divides notes at their headings. When you ask a question, or an agent asks on your behalf, Scry searches the vault and follows the links between notes, and it does not stop at an answer. It points back into the glass at the exact note and section the answer came from, so whatever surfaces can be checked against the source.

## Features

- **Hybrid search** combines dense embeddings with BM25 keyword matching. Paraphrased questions work, and so do exact hostnames, commands and error messages. The default embedding model is multilingual.
- **Link-aware.** Agents can follow links and backlinks from a hit, ranked by relevance to the question. Hub notes such as indexes and daily notes come last.
- **Citable.** Every MCP result has a `url` that opens the note in your browser at the matching heading.
- **Always current.** A file watcher picks up edits within seconds, and a periodic resync catches anything the watcher misses. Changes made while Scry was stopped are detected by content hash.
- **Local-first.** The search engine is embedded Qdrant, the models run on your machine through fastembed, and there is no cloud service and no external database.

## How Scry reads your vault

| In Obsidian | In Scry |
|---|---|
| `[[wikilinks]]`, `[[Note#Heading\|alias]]`, relative `.md` links | Resolved with Obsidian's rules (relative path, vault root, partial path, then shortest file name). They build a link graph for agents and are clickable in the web UI. |
| Properties (`title`, `tags`, `aliases`, `summary`) | Optional and forgiving: broken YAML gives a warning, and the note is still indexed. |
| `#tags` and nested `#a/b` tags | Searchable; `a/b` also matches `a`. |
| Headings | Notes are split into sections at H1 to H3. Every heading gets an anchor, so a citation opens the right section. |
| `%%comments%%`, callouts, embeds | Comments and embeds are left out of search; callout markers are removed. |
| Mermaid diagrams | Rendered in the web UI. |
| `.obsidian/`, `.trash/` | Ignored, as are any folders you exclude. |

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- An Obsidian vault, or any folder of Markdown files
- About 250 MB of disk space for the embedding models, which are downloaded on first start

Scry runs natively on Windows, macOS and Linux. Windows is the main target.

## Quick start

Install Scry once as a [uv tool](https://docs.astral.sh/uv/guides/tools/). This puts the `scry-server` and `scry` commands on your `PATH`:

```bash
git clone <this repo> scry
uv tool install ./scry
```

Then start it in your vault's root folder:

```bash
cd ~/Documents/Vault      # Windows: cd C:\Users\me\Documents\Vault
scry-server
```

- The web UI is at <http://127.0.0.1:8080>. It lists your notes, searches them, and shows index status and warnings.
- The MCP endpoint is at `http://127.0.0.1:8080/mcp`.

Scry treats the current folder as the vault if it contains Obsidian's `.obsidian` folder; otherwise it stops with a message. You can also name the vault, which then needs no `.obsidian` folder, so any folder of Markdown files works: `scry-server ~/Documents/Vault`, or set `SCRY_VAULT_DIR`.

The server answers immediately while the first sync indexes the vault in the background. The `/status` page shows its progress. The first start also downloads the embedding models.

To update Scry later, run `git pull` in the clone, then `uv tool install --reinstall ./scry`.

### Several vaults

Every vault gets its own index under `~/.scry/index/`, named after the vault folder, while the embedding models in `~/.scry/models` are shared. To serve two vaults at once, give the second one another port:

```bash
cd ~/Vaults/Work && scry-server --port 8081
```

## Connecting agents

Scry speaks MCP over streamable HTTP, so any MCP client that supports HTTP servers can use it.

**VS Code** (`.vscode/mcp.json`):

```json
{
  "servers": {
    "scry": { "type": "http", "url": "http://127.0.0.1:8080/mcp" }
  }
}
```

**Claude Code:**

```bash
claude mcp add --transport http scry http://127.0.0.1:8080/mcp
```

### Tools

| Tool | What it does |
|---|---|
| `search` | Hybrid search, optionally filtered by tags. Returns sections with `doc_id`, `url`, title, heading path and text. |
| `get_document` | Full Markdown and metadata of one note. |
| `get_links` | Outgoing links and backlinks of a note, ranked by an optional `query` and capped by `limit`. |
| `list_documents` | All notes, optionally filtered by tag. |
| `reindex` | Re-scans the vault. This is rarely needed, because the watcher keeps the index current. |

The server's MCP instructions tell agents to search first, read the full note when the hit is incomplete, follow a few links when a note points elsewhere, and **cite every note as a Markdown link to its `url`**.

### Copilot agent

[`.github/agents/scry.agent.md`](.github/agents/scry.agent.md) defines a GitHub Copilot custom agent. It answers only from your notes, keeps commands and config values exactly as written, and ends each answer with a list of linked sources. Pick **scry** in the Copilot Chat agent picker.

### Citation links

Links in results start with `http://<host>:<port>` by default. If you open the web UI under a different address, for example through a reverse proxy with HTTPS, set `SCRY_PUBLIC_URL` to that address so the links agents give you work in your browser.

## Configuration

All settings are environment variables with the `SCRY_` prefix. A wrong value stops Scry with a one-line message naming the variable.

| Variable | Default | Meaning |
|---|---|---|
| `SCRY_VAULT_DIR` | current folder | The vault folder. Without it, the current folder must contain `.obsidian`. `scry-server <folder>` overrides it. |
| `SCRY_INDEX_DIR` | `~/.scry/index/<vault>-<hash>` | Where the search index lives: one per vault, derived from the vault's full path. It must not be inside the vault. |
| `SCRY_MODEL_CACHE` | `~/.scry/models` | Downloaded embedding models. |
| `SCRY_EXCLUDE` | *(none)* | Comma-separated globs relative to the vault, for example `Templates,Archive/**/*.md`. A folder name excludes everything below it. |
| `SCRY_HOST` / `SCRY_PORT` | `127.0.0.1` / `8080` | Where the server listens. `scry-server --port` overrides the port. |
| `SCRY_PUBLIC_URL` | `http://<host>:<port>` | Base of the citation links in MCP results. |
| `SCRY_WATCH` | `true` | Watch the vault for changes. |
| `SCRY_RESYNC_INTERVAL` | `600` | Seconds between safety resyncs; `0` turns them off. |
| `SCRY_HUB_DEGREE` | `30` | Notes with at least this many linked neighbours count as hubs. |
| `SCRY_LINKS_LIMIT` | `10` | Default number of links returned per list (outgoing links and backlinks). |
| `SCRY_CHUNK_MAX_CHARS` | `1500` | Maximum size of an indexed section. |
| `SCRY_DENSE_MODEL` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | Embedding model. After changing it, delete the index folder so that every note is embedded again. |
| `SCRY_SPARSE_MODEL` | `Qdrant/bm25` | Keyword model. |
| `SCRY_SYSTEM_CERTS` | `true` | Check HTTPS certificates against the operating system's certificate store instead of Python's bundled one. See [Corporate networks](#corporate-networks). |

If your vault is on a network share, or on a Windows drive seen from WSL, file events may not arrive. Set `WATCHFILES_FORCE_POLLING=true` in that case.

## Corporate networks

Scry needs the network only once, to download the embedding models on first start. Company networks often get in the way.

**TLS inspection.** Many company proxies decrypt HTTPS and re-sign it with the company's own root certificate. Python's bundled certificate list doesn't contain that certificate, so downloads fail with certificate errors. Scry therefore checks certificates against your operating system's certificate store, where IT installs the company certificate, the same store your browser uses. This works without any configuration. Setting `REQUESTS_CA_BUNDLE` doesn't help here, because the model download uses `httpx`, which ignores it. If you do point Python at a certificate file, use `SSL_CERT_FILE`, and write the path without quotes: a quoted path makes Windows fail with `[Errno 22] Invalid argument`. To turn the system store off, for example on a minimal Linux install without one, set `SCRY_SYSTEM_CERTS=false`.

**Redirected home folders.** If your home folder lives on OneDrive or a network share, file locking and renaming during the download can fail. Keep the models and the index on a local disk:

```powershell
$env:SCRY_MODEL_CACHE = "C:\scry\models"
$env:SCRY_INDEX_DIR = "C:\scry\index"
```

**Blocked downloads.** If the proxy blocks Hugging Face entirely, copy the models folder from a machine where the download worked. Scry only reads it, so a copied folder works offline.

## Command line

Like the server, `scry` works on the vault in the current folder, or on `SCRY_VAULT_DIR`:

```bash
scry sync                                     # update the index once
scry search "restic backup" -k 5 -t homelab
scry links "Homelab/NAS Backup.md" -q "restore"
```

Only one process can hold the index. While `scry-server` is running, the CLI refuses to start (exit code 2). The server keeps the index in sync on its own.

## Security

Scry has **no authentication**. Anyone who can reach the port can read your whole vault and trigger a re-index. Keep the default `127.0.0.1` binding. If you need access from other machines, put Scry behind a proxy that authenticates, for example with basic auth, mTLS, Tailscale or Cloudflare Access.

The MCP endpoint only accepts the host names `localhost`, `127.0.0.1` and `[::1]`, as protection against DNS rebinding. Reaching it under another name needs a change in `scry/bootstrap.py`.

## Development

The devcontainer is for development only and points `SCRY_VAULT_DIR` at `./data/knowledge`.

```bash
uv run pytest            # fast suite with fake models
uv run pytest -m models  # smoke test with the real models (downloads ~250 MB)
uv run ruff check && uv run ruff format
uv run pyright           # strict
uv run lint-imports      # architecture contracts
```

The code is hexagonal: a pure domain, ports, use cases and adapters, with the layers enforced by import-linter. [CLAUDE.md](CLAUDE.md) describes the architecture, the invariants and the library quirks. [docs/SPEC.md](docs/SPEC.md) is the original design.

## License

No license has been chosen yet.
