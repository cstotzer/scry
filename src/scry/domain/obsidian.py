"""Obsidian Markdown syntax: links, inline tags and the cleanup applied before embedding."""

import re
from collections.abc import Callable
from urllib.parse import unquote

from scry.domain.model import Link

_FENCE = re.compile(r"^\s*(```|~~~)")
_INLINE_CODE = re.compile(r"(`+)(?:(?!\1).)+?\1")
_COMMENT = re.compile(r"%%.*?%%", re.DOTALL)
_WIKILINK = re.compile(r"(!?)\[\[([^\[\]|#\n]*)(?:#([^\[\]|\n]*))?(?:\|([^\[\]\n]*))?\]\]")
_MD_LINK = re.compile(r"(!?)\[[^\]\n]*\]\((<[^>\n]+>|[^)\s]+)\)")
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
_INLINE_TAG = re.compile(r"(?<!\S)#([\w/-]*[^\W\d_][\w/-]*)")
_CALLOUT = re.compile(r"^(\s*(?:>\s*)+)\[![^\]\n]+\][+-]?\s*", re.MULTILINE)


def mask_code(text: str) -> str:
    """Blank out fenced code blocks, inline code and %%comments%%, keeping every offset."""
    lines: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
            lines.append(" " * len(line))
        elif in_fence:
            lines.append(" " * len(line))
        else:
            lines.append(_INLINE_CODE.sub(lambda m: " " * len(m.group(0)), line))
    masked = "\n".join(lines)
    return _COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), masked)


def extract_links(body: str) -> list[Link]:
    """Wikilinks, embeds and Markdown links to notes, in order of appearance."""
    text = mask_code(body)
    found: list[tuple[int, Link]] = []
    for m in _WIKILINK.finditer(text):
        target = m.group(2).strip().removesuffix("\\")  # `[[a\|b]]` inside tables
        if target:  # `[[#Heading]]` points into the note itself
            heading = (m.group(3) or "").strip() or None
            found.append((m.start(), Link(target, heading, embed=bool(m.group(1)))))
    for m in _MD_LINK.finditer(text):
        href = m.group(2).removeprefix("<").removesuffix(">")
        if _SCHEME.match(href):
            continue  # http:, mailto:, obsidian: ...
        path, _, heading = unquote(href).partition("#")
        if path.lower().endswith(".md"):
            found.append((m.start(), Link(path, heading or None, embed=bool(m.group(1)))))
    return [link for _, link in sorted(found, key=lambda pair: pair[0])]


def replace_wikilinks(body: str, render: Callable[[Link, str], str]) -> str:
    """Replace each wikilink outside code with `render(link, display_text)`.

    `[[#Heading]]` points into the note itself and arrives with an empty target.
    """
    masked = mask_code(body)
    out: list[str] = []
    pos = 0
    for m in _WIKILINK.finditer(masked):
        target = m.group(2).strip().removesuffix("\\")
        heading = (m.group(3) or "").strip() or None
        if not target and not heading:
            continue
        link = Link(target, heading, embed=bool(m.group(1)))
        default = f"{target} > {heading}" if target and heading else target or heading or ""
        display = (m.group(4) or "").strip() or default
        out += [body[pos : m.start()], render(link, display)]
        pos = m.end()
    return "".join([*out, body[pos:]])


def normalize_tag(raw: str) -> list[str]:
    """`#Project/Work` -> ["project", "project/work"]: nested tags also match their parents."""
    tag = re.sub(r"\s+", "-", raw.strip().lstrip("#").strip().lower()).strip("/")
    parts = [p for p in tag.split("/") if p]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def normalize_tags(raw: list[str]) -> list[str]:
    tags: list[str] = []
    for value in raw:
        for tag in normalize_tag(value):
            if tag not in tags:
                tags.append(tag)
    return tags


def extract_inline_tags(body: str) -> list[str]:
    return [m.group(1) for m in _INLINE_TAG.finditer(mask_code(body))]


def _wikilink_text(m: re.Match[str]) -> str:
    if m.group(1):
        return ""  # embeds (images, transclusions) carry no text of their own
    return (m.group(4) or m.group(2) or (m.group(3) or "").lstrip("^")).strip()


def clean_for_embedding(text: str) -> str:
    """Reduce Obsidian syntax to the words a reader sees."""
    text = _COMMENT.sub("", text)
    text = _WIKILINK.sub(_wikilink_text, text)
    return _CALLOUT.sub(r"\1", text)
