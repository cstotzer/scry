import socket
import threading
import time
from collections.abc import Generator

import pytest
import uvicorn
from fastapi.testclient import TestClient
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
        assert doc.structured_content["sections"] == [
            {"heading_path": ["Docker"], "url": "https://scry.example/notes/net/proxy.md#docker"}
        ]

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


def _mcp_status(settings: Settings, host: str, origin: str | None = None) -> int:
    headers = {"Host": host, "Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    with TestClient(create_app(settings, FakeEmbedder())) as client:
        return client.post("/mcp", headers=headers, content="{}").status_code


@pytest.mark.parametrize(
    ("update", "host", "origin", "allowed"),
    [
        ({}, "localhost:8080", None, True),
        ({}, "host.docker.internal:8080", None, False),
        ({"allowed_hosts": ["host.docker.internal"]}, "host.docker.internal:8080", None, True),
        ({"allowed_hosts": ["host.docker.internal"]}, "evil.example", None, False),
        ({"public_url": "https://scry.corp/"}, "scry.corp", "https://scry.corp", True),
        ({"public_url": "https://scry.corp/"}, "scry.corp", "https://evil.example", False),
        ({"allowed_hosts": ["*"]}, "anything:1234", None, True),
    ],
)
def test_mcp_host_check(
    settings: Settings, update: dict[str, object], host: str, origin: str | None, allowed: bool
) -> None:
    status = _mcp_status(settings.model_copy(update=update), host, origin)
    assert (status not in (403, 421)) == allowed, status
