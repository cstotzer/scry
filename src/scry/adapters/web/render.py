"""Note body -> HTML, with links resolved like Obsidian and an id on every heading."""

import re
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token

from scry.adapters.web.anchors import heading_fragment, heading_slug, note_href
from scry.domain import DocumentId, Link, LinkResolver, replace_wikilinks

_COMMENT = re.compile(r"%%.*?%%", re.DOTALL)
_markdown = MarkdownIt("commonmark", {"html": False}).enable("table")


@dataclass(frozen=True)
class NoteSection:
    """A heading of a note and the link to it on the note's page."""

    heading_path: list[str]
    href: str


def render_note(doc_id: DocumentId, body: str, resolver: LinkResolver) -> str:
    return _markdown.renderer.render(_parse(doc_id, body, resolver), _markdown.options, {})


def note_sections(doc_id: DocumentId, body: str, resolver: LinkResolver) -> list[NoteSection]:
    """Every heading with the exact anchor the page gives it, repeated headings included."""
    sections: list[NoteSection] = []
    stack: list[tuple[int, str]] = []
    tokens = _parse(doc_id, body, resolver)
    for i, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        level = int(token.tag[1:])
        text = "".join(
            c.content for c in tokens[i + 1].children or [] if c.type in ("text", "code_inline")
        ).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, text))
        href = f"{note_href(doc_id)}#{quote(str(token.attrGet('id')))}"
        sections.append(NoteSection([t for _, t in stack], href))
    return sections


def _parse(doc_id: DocumentId, body: str, resolver: LinkResolver) -> list[Token]:
    generated: set[str] = set()  # hrefs written for wikilinks, already resolved

    def href(link: Link) -> str | None:
        heading = link.heading.rsplit("#", 1)[-1] if link.heading else None  # [[N#A#B]] -> B
        if not link.target:
            return heading_fragment(heading) or None
        target = resolver.resolve(link, doc_id)
        return None if target is None else note_href(target, heading)

    def wikilink(link: Link, display: str) -> str:
        if link.embed:
            return f"`{display}`"  # attachments are not served
        if (url := href(link)) is None:
            return f"*{display}*"
        generated.add(url)
        label = display.replace("[", r"\[").replace("]", r"\]")
        return f"[{label}]({url})"

    def resolve_markdown_link(token: Token) -> None:
        url = str(token.attrGet("href") or "")
        parts = urlsplit(url)
        if url in generated or parts.scheme or parts.netloc:
            return
        path, _, heading = unquote(url).partition("#")
        if path.lower().endswith(".md") and (resolved := href(Link(path, heading or None))):
            token.attrSet("href", resolved)

    slugs: set[str] = set()

    def unique(slug: str) -> str:
        candidate, n = slug, 0
        while candidate in slugs:  # repeated headings get -1, -2, ... like GitHub
            n += 1
            candidate = f"{slug}-{n}"
        slugs.add(candidate)
        return candidate

    tokens = _markdown.parse(replace_wikilinks(_COMMENT.sub("", body), wikilink))
    for i, token in enumerate(tokens):
        if token.type == "heading_open":
            token.attrSet("id", unique(heading_slug(tokens[i + 1].content)))
        for child in token.children or []:
            if child.type == "link_open":
                resolve_markdown_link(child)
    return tokens
