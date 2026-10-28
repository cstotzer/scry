from typing import Protocol

from scry.domain import Document, DocumentId


class MarkdownParser(Protocol):
    def parse(self, doc_id: DocumentId, raw: str) -> Document:
        """Never rejects a note; problems such as broken YAML end up in `Document.warnings`."""
        ...
