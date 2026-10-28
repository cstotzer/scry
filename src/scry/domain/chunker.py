import re

from scry.domain.model import Chunk, Document
from scry.domain.obsidian import clean_for_embedding

_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


class MarkdownChunker:
    """Splits a document body into heading sections (H1-H3), then by paragraph."""

    def __init__(self, max_chars: int) -> None:
        if max_chars < 1:
            raise ValueError("max_chars must be positive")
        self.max_chars = max_chars

    def chunk(self, doc: Document) -> list[Chunk]:
        title = doc.meta.title
        chunks: list[Chunk] = []
        # A document without body text still gets one chunk, so it stays findable and indexed.
        sections = self._sections(doc.body) or [([], doc.meta.summary or title)]
        for path, text in sections:
            for piece in self._split(text):
                prefix = " > ".join([title, *path])
                chunks.append(
                    Chunk(
                        doc_id=doc.id,
                        index=len(chunks),
                        heading_path=path,
                        text=piece,
                        embed_text=f"{prefix}\n\n{clean_for_embedding(piece)}",
                    )
                )
        return chunks

    def _sections(self, body: str) -> list[tuple[list[str], str]]:
        sections: list[tuple[list[str], str]] = []
        path: list[str] = []
        lines: list[str] = []
        in_fence = False

        def flush() -> None:
            text = "\n".join(lines).strip()
            if text:
                sections.append((list(path), text))
            lines.clear()

        for line in body.splitlines():
            if _FENCE.match(line):
                in_fence = not in_fence
            match = None if in_fence else _HEADING.match(line)
            if match:
                flush()
                level = len(match.group(1))
                path[:] = [*path[: level - 1], match.group(2)]
            else:
                lines.append(line)
        flush()
        return sections

    def _split(self, text: str) -> list[str]:
        if len(text) <= self.max_chars:
            return [text]
        pieces: list[str] = []
        current = ""
        for para in (p.strip() for p in re.split(r"\n\s*\n", text)):
            if not para:
                continue
            candidate = f"{current}\n\n{para}" if current else para
            if len(candidate) <= self.max_chars:
                current = candidate
                continue
            if current:
                pieces.append(current)
            while len(para) > self.max_chars:
                pieces.append(para[: self.max_chars])
                para = para[self.max_chars :]
            current = para
        if current:
            pieces.append(current)
        return pieces
