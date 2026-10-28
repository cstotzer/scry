"""URLs of note pages and the ids of their headings."""

import re
from urllib.parse import quote

from scry.domain import DocumentId, replace_wikilinks

_MD_LINK_TEXT = re.compile(r"!?\[([^\]\n]*)\]\([^)\n]*\)")
_NON_SLUG = re.compile(r"[^\w\s-]")


def heading_slug(heading: str) -> str:
    """Anchor id of a heading: `## Docker [[Daemon|setup]]` -> `docker-setup`.

    Works on the heading as written and on its rendered source, where wikilinks have already
    become Markdown links with the same display text, so both give the same id.
    """
    text = replace_wikilinks(heading, lambda _, display: display)
    text = _NON_SLUG.sub("", _MD_LINK_TEXT.sub(r"\1", text)).strip().lower()
    return re.sub(r"\s+", "-", text) or "section"


def heading_fragment(heading: str | None) -> str:
    """`#slug` for a heading; empty for none or a block reference (`^id`), which has no anchor."""
    if not heading or heading.startswith("^"):
        return ""
    return "#" + quote(heading_slug(heading))


def note_href(doc_id: DocumentId, heading: str | None = None) -> str:
    """Path of a note's page, pointing at `heading` when given."""
    return f"/notes/{quote(doc_id.value)}{heading_fragment(heading)}"
