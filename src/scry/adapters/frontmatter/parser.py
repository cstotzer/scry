import posixpath
import re
from typing import Any, cast

import yaml

from scry.domain import (
    Document,
    DocumentId,
    NoteMeta,
    content_hash,
    extract_inline_tags,
    extract_links,
    normalize_tags,
)

_BLOCK = re.compile(r"\A﻿?---[ \t]*\n(.*?)\n?(?:---|\.\.\.)[ \t]*(?:\n|\Z)", re.DOTALL)


def _strings(value: Any) -> list[str]:
    """Obsidian list properties may also be written as one comma or space separated string."""
    if value is None:
        return []
    if isinstance(value, str):
        return [v for v in re.split(r"[,\s]+", value) if v]
    if isinstance(value, list):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    return [str(value)]


def _text(value: Any) -> str | None:
    return str(value).strip() or None if value is not None else None


class FrontMatterParser:
    """Parses Obsidian notes. Properties are optional; unknown ones are ignored."""

    def parse(self, doc_id: DocumentId, raw: str) -> Document:
        text = raw.replace("\r\n", "\n")
        props: dict[str, Any] = {}
        warnings: list[str] = []
        body = text.removeprefix("﻿")
        if match := _BLOCK.match(text):
            body = text[match.end() :]
            try:
                loaded = yaml.safe_load(match.group(1))
            except yaml.YAMLError as exc:
                warnings.append(f"properties ignored, invalid YAML: {exc}")
            else:
                if isinstance(loaded, dict):
                    props = {str(k): v for k, v in cast(dict[Any, Any], loaded).items()}
                elif loaded is not None:
                    warnings.append("properties ignored, expected key: value pairs")
        stem = posixpath.basename(doc_id.value).removesuffix(".md")
        aliases = _strings(props.get("aliases", props.get("alias")))
        meta = NoteMeta(
            title=_text(props.get("title")) or stem,
            tags=normalize_tags(
                _strings(props.get("tags", props.get("tag"))) + extract_inline_tags(body)
            ),
            aliases=aliases,
            summary=_text(props.get("summary", props.get("description"))),
        )
        return Document(
            id=doc_id,
            meta=meta,
            body=body,
            content_hash=content_hash(raw),
            links=extract_links(body),
            warnings=warnings,
        )
