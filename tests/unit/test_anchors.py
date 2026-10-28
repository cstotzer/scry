from scry.adapters.web.anchors import heading_slug, note_href
from scry.domain import DocumentId


def test_heading_slug() -> None:
    assert heading_slug("Daemon config") == "daemon-config"
    assert heading_slug("  Ä/B: ü?  x ") == "äb-ü-x"
    assert heading_slug("**Bold** `code`") == "bold-code"
    assert heading_slug("!!!") == "section"


def test_heading_slug_is_the_same_before_and_after_wikilink_rendering() -> None:
    written = "Plan [[Docker|daemon]] [[Proxy#Port]] [[Ghost]]"
    rendered = r"Plan [daemon](/notes/Docker.md) [Proxy \> Port](/notes/Proxy.md#port) *Ghost*"
    assert heading_slug(written) == heading_slug(rendered) == "plan-daemon-proxy-port-ghost"


def test_note_href_quotes_path_and_heading() -> None:
    doc = DocumentId("a b/Ä (1).md")
    assert note_href(doc) == "/notes/a%20b/%C3%84%20%281%29.md"
    assert note_href(doc, "Über uns").endswith("#%C3%BCber-uns")
    assert note_href(doc, "^block") == note_href(doc)
