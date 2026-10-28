import hashlib
import os
from pathlib import Path
from typing import Annotated, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_HOME = Path.home() / ".scry"


def default_index_dir(vault_dir: Path) -> Path:
    """One index per vault, so vaults can be switched and served side by side."""
    vault = vault_dir.resolve()
    digest = hashlib.sha256(os.path.normcase(str(vault)).encode()).hexdigest()[:8]
    return _HOME / "index" / f"{vault.name or 'vault'}-{digest}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCRY_")

    vault_dir: Path  # defaults to the current folder if it is an Obsidian vault
    index_dir: Path  # defaults to default_index_dir(vault_dir)
    model_cache: Path = _HOME / "models"
    # Comma-separated globs relative to the vault, e.g. "Templates,Archive/**/*.md".
    exclude: Annotated[list[str], NoDecode] = []
    watch: bool = True
    resync_interval: int = 600  # seconds between safety syncs; 0 disables them
    hub_degree: int = 30  # notes with this many distinct neighbours count as hubs
    links_limit: int = 10
    dense_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    sparse_model: str = "Qdrant/bm25"
    host: str = "127.0.0.1"
    port: int = 8080
    # Base of the note links in MCP results, as the user's browser reaches the server,
    # e.g. behind a reverse proxy. Defaults to http://<host>:<port>.
    public_url: str | None = None
    chunk_max_chars: int = 1500
    # Verify TLS against the OS certificate store, which on corporate machines also holds the
    # root of TLS-inspecting proxies; off falls back to certifi's bundle.
    system_certs: bool = True

    @model_validator(mode="before")
    @classmethod
    def _split_exclude(cls, data: dict[str, object]) -> dict[str, object]:
        if isinstance(value := data.get("exclude"), str):
            data["exclude"] = [p.strip() for p in value.split(",") if p.strip()]
        return data

    @model_validator(mode="before")
    @classmethod
    def _vault_defaults(cls, data: dict[str, object]) -> dict[str, object]:
        if not data.get("vault_dir"):
            cwd = Path.cwd()
            if not (cwd / ".obsidian").is_dir():
                raise ValueError(
                    f"{cwd} is not an Obsidian vault (it has no .obsidian folder). "
                    "Run scry in your vault's root folder, pass the vault folder, "
                    "or set SCRY_VAULT_DIR."
                )
            data["vault_dir"] = cwd
        if not data.get("index_dir"):
            data["index_dir"] = default_index_dir(Path(str(data["vault_dir"])))
        return data

    @model_validator(mode="after")
    def _index_outside_vault(self) -> Self:
        if self.index_dir.resolve().is_relative_to(self.vault_dir.resolve()):
            raise ValueError("SCRY_INDEX_DIR must not be inside the vault")
        return self
