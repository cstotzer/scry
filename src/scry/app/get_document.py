from scry.domain import Document, DocumentId
from scry.ports import DocumentStore, MarkdownParser


class GetDocument:
    def __init__(self, store: DocumentStore, parser: MarkdownParser) -> None:
        self._store, self._parser = store, parser

    def raw(self, doc_id: DocumentId) -> str:
        return self._store.read_raw(doc_id)

    def __call__(self, doc_id: DocumentId) -> Document:
        return self._parser.parse(doc_id, self._store.read_raw(doc_id))
