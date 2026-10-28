import hashlib
import os
import tomllib
from pathlib import Path
from typing import Annotated, Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_HOME = Path.home() / ".scry"

VAULT_CONFIG = ".scry.toml"
# Settings that belong to a vault rather than a machine: paths, models and TLS stay in SCRY_*.
VAULT_CONFIG_KEYS = frozenset(
    [
        "title",
        "exclude",
        "port",
        "host",
        "public_url",
        "allowed_hosts",
        "watch",
        "resync_interval",
        "hub_degree",
        "links_limit",
    ]
)


def read_vault_config(vault_dir: Path) -> dict[str, object]:
    """The settings in `<vault>/.scry.toml`, or none if the file does not exist."""
    path = vault_dir / VAULT_CONFIG
    try:
        with path.open("rb") as f:
            values = tomllib.load(f)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{path}: {exc}") from exc
    if unknown := sorted(set(values) - VAULT_CONFIG_KEYS):
        raise ValueError(
            f"{path}: unknown setting(s) {', '.join(unknown)}; "
            f"allowed: {', '.join(sorted(VAULT_CONFIG_KEYS))}"
        )
    return values


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
    title: str | None = None  # shown as "Scry | <title>" in the web UI
    dense_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    sparse_model: str = "Qdrant/bm25"
    host: str = "127.0.0.1"
    port: int = 8080
    # Base of the note links in MCP results, as the user's browser reaches the server,
    # e.g. behind a reverse proxy. Defaults to http://<host>:<port>.
    public_url: str | None = None
    # Extra Host names the MCP endpoint answers to (DNS-rebinding protection), e.g.
    # "host.docker.internal". localhost and public_url's host are always allowed; "*" allows any.
    allowed_hosts: Annotated[list[str], NoDecode] = []
    chunk_max_chars: int = 1500
    # Verify TLS against the OS certificate store, which on corporate machines also holds the
    # root of TLS-inspecting proxies; off falls back to certifi's bundle.
    system_certs: bool = True

    @field_validator("exclude", "allowed_hosts", mode="before")
    @classmethod
    def _split_list(cls, value: object) -> object:
        if isinstance(value, str):
            return [p.strip() for p in value.split(",") if p.strip()]
        return value

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
        vault = Path(str(data["vault_dir"]))
        # Lowest priority: arguments and SCRY_* variables override the vault's file.
        data = {**read_vault_config(vault), **data}
        if not data.get("index_dir"):
            data["index_dir"] = default_index_dir(vault)
        return data

    @model_validator(mode="after")
    def _index_outside_vault(self) -> Self:
        if self.index_dir.resolve().is_relative_to(self.vault_dir.resolve()):
            raise ValueError("SCRY_INDEX_DIR must not be inside the vault")
        return self
