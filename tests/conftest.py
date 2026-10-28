from pathlib import Path

import pytest

from scry.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    vault = tmp_path / "vault"
    vault.mkdir()
    return Settings(
        vault_dir=vault,
        index_dir=tmp_path / "index",
        model_cache=tmp_path / "models",
        chunk_max_chars=500,
        watch=False,
        resync_interval=0,
    )
