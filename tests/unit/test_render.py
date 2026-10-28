from scry.adapters.web.render import note_sections, render_note
from scry.domain import DocumentId, LinkResolver

DOC = DocumentId("ops/Server A.md")
RESOLVER = LinkResolver([DOC, DocumentId("Docker.md")])
BODY = (
    "# Server A\n"
    "## Notes\n"
    "### Disk `sda`\n"
    "## Setup [[Docker|the daemon]]\n"
    "### Notes\n"
    "```\n# not a heading\n```\n"
)


def test_sections_carry_heading_paths_and_the_anchors_of_the_page() -> None:
    sections = note_sections(DOC, BODY, RESOLVER)
    assert [(s.heading_path, s.href) for s in sections] == [
        (["Server A"], "/notes/ops/Server%20A.md#server-a"),
        (["Server A", "Notes"], "/notes/ops/Server%20A.md#notes"),
        (["Server A", "Notes", "Disk sda"], "/notes/ops/Server%20A.md#disk-sda"),
        (["Server A", "Setup the daemon"], "/notes/ops/Server%20A.md#setup-the-daemon"),
        (["Server A", "Setup the daemon", "Notes"], "/notes/ops/Server%20A.md#notes-1"),
    ]
    html = render_note(DOC, BODY, RESOLVER)
    for section in sections:
        assert f'id="{section.href.split("#")[1]}"' in html
