"""Smoke test with the real fastembed models. Run with `uv run pytest -m models`."""

import os
from pathlib import Path

import pytest

from scry.adapters.fastembed import FastEmbedEmbedder
from scry.bootstrap import open_services
from scry.config import Settings
from scry.domain import DocumentId
from tests.fakes import md

pytestmark = pytest.mark.models

DOCS = {
    "ops/proxy.md": md(
        "Proxy setup for corporate network",
        "# Docker\nSet HTTP_PROXY to http://proxy01.corp.example:3128 in the Docker daemon "
        "config.\n# uv\nExport HTTPS_PROXY before running uv sync.",
        ["network"],
    ),
    "cooking/bread.md": md(
        "Sourdough bread",
        "# Dough\nMix flour, water and starter, then let it rise overnight.",
        ["food"],
    ),
    "ops/backup.md": md(
        "Laptop backups",
        "# Schedule\nTime Machine runs hourly to the NAS at nas.home.lan.",
        ["ops"],
    ),
}


def test_hybrid_search_with_real_models(tmp_path: Path) -> None:
    cache = Path(os.environ.get("SCRY_MODEL_CACHE", Path.home() / ".cache" / "scry-models"))
    (tmp_path / "vault").mkdir()
    settings = Settings(
        vault_dir=tmp_path / "vault", index_dir=tmp_path / "index", model_cache=cache
    )
    for doc_id, raw in DOCS.items():
        path = settings.vault_dir / doc_id
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw)
    embedder = FastEmbedEmbedder(settings.dense_model, settings.sparse_model, cache)
    with open_services(settings, embedder) as services:
        assert len(services.sync().added) == 3

        def top(query: str) -> DocumentId:
            return services.search(query, 3)[0].doc_id

        assert top("proxy01.corp.example") == DocumentId("ops/proxy.md")
        assert top("nas.home.lan") == DocumentId("ops/backup.md")
        assert top("Wie stelle ich den Proxy für Docker ein?") == DocumentId("ops/proxy.md")
        assert top("Wie backe ich Brot?") == DocumentId("cooking/bread.md")
