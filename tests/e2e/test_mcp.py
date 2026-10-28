import socket
import threading
import time
from collections.abc import Generator

import pytest
import uvicorn
from mcp import Client

from scry.bootstrap import create_app
from scry.config import Settings
from tests.fakes import FakeEmbedder, md, wait_for_sync


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server_url(settings: Settings) -> Generator[str]:
    vault = settings.vault_dir
    (vault / "net").mkdir()
    (vault / "net/proxy.md").write_text(
        md("Proxy setup", "# Docker\nUse proxy01.corp.example:3128, see [[Daemon]].", ["network"])
    )
    (vault / "Daemon.md").write_text("Docker daemon config: /etc/docker/daemon.json")
    port = _free_port()
    app = create_app(
        settings.model_copy(update={"public_url": "https://scry.example/"}), FakeEmbedder()
    )
    server = uvicorn.Server(uvicorn.Config(app, port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    wait_for_sync(app.state.services)
    yield f"http://127.0.0.1:{port}/mcp"
    server.should_exit = True
    thread.join(10)


@pytest.mark.anyio
async def test_mcp_tools(server_url: str, settings: Settings) -> None:
    async with Client(server_url) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        assert tools == {"search", "get_document", "get_links", "list_documents", "reindex"}

        found = await client.call_tool("search", {"query": "proxy01.corp.example"})
        assert not found.is_error
        assert found.structured_content is not None
        top = found.structured_content["result"][0]
        assert (top["doc_id"], top["heading_path"]) == ("net/proxy.md", ["Docker"])
        assert top["url"] == "https://scry.example/notes/net/proxy.md#docker"

        doc = await client.call_tool("get_document", {"doc_id": "net/proxy.md"})
        assert doc.structured_content is not None
        assert "proxy01" in doc.structured_content["body"]
        assert doc.structured_content["outgoing_links"] == 1
        assert doc.structured_content["url"] == "https://scry.example/notes/net/proxy.md"

        links = await client.call_tool("get_links", {"doc_id": "Daemon.md", "query": "proxy"})
        assert links.structured_content is not None
        assert [r["doc_id"] for r in links.structured_content["backlinks"]] == ["net/proxy.md"]
        assert links.structured_content["truncated"] is False

        missing = await client.call_tool("get_document", {"doc_id": "nope.md"})
        assert missing.is_error

        (settings.vault_dir / "net/proxy.md").unlink()
        report = await client.call_tool("reindex", {})
        assert report.structured_content is not None
        assert report.structured_content["removed"] == ["net/proxy.md"]
        listing = await client.call_tool("list_documents", {})
        assert listing.structured_content is not None
        assert [d["doc_id"] for d in listing.structured_content["result"]] == ["Daemon.md"]
