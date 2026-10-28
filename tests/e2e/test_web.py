from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from scry.bootstrap import create_app
from scry.config import Settings
from tests.fakes import FakeEmbedder, md, wait_for_sync


@pytest.fixture
def client(settings: Settings) -> Generator[TestClient]:
    vault = settings.vault_dir
    (vault / "ops").mkdir()
    (vault / "ops/Proxy.md").write_text(
        md(
            "Proxy",
            "# Docker\nuse squid.corp.example, see [[Docker|the daemon]] and [[Ghost]]\n"
            "<script>alert(1)</script> %%secret%%",
            ["network"],
        )
    )
    (vault / "Docker.md").write_text("Daemon notes #ops\n\n```\n[[NotALink]]\n```")
    (vault / "broken.md").write_text("---\ntitle: [x\n---\nbody")
    (vault / "ops/Anchors.md").write_text(
        "# Setup\n## Notes\n## Notes\n"
        "[[Docker#Daemon config|cfg]] [[ops/Proxy#Docker]] [[#Setup]] [[Docker#^block]]\n"
        "[rel](Proxy.md#Docker) [web](https://x.org/a.md) [gone](Gone.md)"
    )
    app = create_app(settings, FakeEmbedder())
    with TestClient(app) as c:
        wait_for_sync(app.state.services)
        yield c


def test_list_and_tags(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert "Proxy" in page.text and 'href="/notes/ops/Proxy.md"' in page.text
    assert "Docker.md" in client.get("/?tag=ops").text
    assert "ops/Proxy.md" not in client.get("/?tag=ops").text


def test_note_view_renders_links_and_backlinks(client: TestClient) -> None:
    page = client.get("/notes/ops/Proxy.md").text
    assert '<a href="/notes/Docker.md">the daemon</a>' in page
    assert "<em>Ghost</em>" in page  # unresolved
    assert "<script>" not in page and "secret" not in page
    docker = client.get("/notes/Docker.md").text
    assert "Backlinks (2)" in docker and 'href="/notes/ops/Proxy.md"' in docker
    assert "[[NotALink]]" in docker  # code stays code
    assert client.get("/notes/missing.md").status_code == 404
    assert client.get("/notes/..%2Fescape.md").status_code == 404


def test_note_view_has_heading_anchors_and_links_into_them(client: TestClient) -> None:
    page = client.get("/notes/ops/Anchors.md").text
    assert '<h1 id="setup">' in page
    assert '<h2 id="notes">' in page and '<h2 id="notes-1">' in page
    assert '<a href="/notes/Docker.md#daemon-config">cfg</a>' in page
    assert 'href="/notes/ops/Proxy.md#docker"' in page
    assert '<a href="#setup">Setup</a>' in page
    assert 'href="/notes/Docker.md">Docker &gt; ^block</a>' in page  # block refs have no anchor
    assert '<a href="/notes/ops/Proxy.md#docker">rel</a>' in page  # Markdown links resolve too
    assert '<a href="https://x.org/a.md">web</a>' in page
    assert '<a href="Gone.md">gone</a>' in page  # unresolved: left as written
    assert '<h1 id="docker">' in client.get("/notes/ops/Proxy.md").text


def test_mermaid_script_loads_only_for_notes_with_diagrams(
    client: TestClient, settings: Settings
) -> None:
    (settings.vault_dir / "Flow.md").write_text("```mermaid\ngraph LR\n  A[[Proxy]] --> B\n```")
    page = client.get("/notes/Flow.md").text
    assert '<code class="language-mermaid">' in page and "A[[Proxy]] --&gt; B" in page
    assert "mermaid.min.js" in page
    assert "mermaid.min.js" not in client.get("/notes/ops/Proxy.md").text
    assert client.get("/static/mermaid.min.js").status_code == 200


def test_status_shows_warnings_and_editing_is_gone(client: TestClient) -> None:
    status = client.get("/status").text
    assert "4 documents indexed" in status
    assert "broken.md" in status and "invalid YAML" in status
    assert client.get("/docs/new").status_code == 404
    assert client.post("/docs/x.md", data={"raw": "x"}).status_code in (404, 405)


def test_search(client: TestClient) -> None:
    page = client.get("/search", params={"q": "squid.corp.example"}).text
    assert 'href="/notes/ops/Proxy.md#docker"' in page  # straight to the matching section


def test_resync_picks_up_changes(client: TestClient, settings: Settings) -> None:
    (settings.vault_dir / "Docker.md").unlink()
    resp = client.post("/status/resync", follow_redirects=False)
    assert resp.status_code == 303
    assert "3 documents indexed" in client.get("/status").text


def test_custom_title(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"title": "Work"}), FakeEmbedder())
    with TestClient(app) as c:
        page = c.get("/search").text
    assert "<strong>Scry</strong> | Work</a>" in page
    assert "<title>Search · Scry | Work</title>" in page


def test_no_custom_title(client: TestClient) -> None:
    page = client.get("/search").text
    assert "<strong>Scry</strong></a>" in page and "<title>Search · Scry</title>" in page
