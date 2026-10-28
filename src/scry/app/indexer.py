from dataclasses import dataclass

from scry.domain import Document, MarkdownChunker
from scry.ports import Embedder, VectorIndex


@dataclass(frozen=True)
class Indexer:
    """Chunks, embeds and writes one document to the index. Callers hold the write lock."""

    chunker: MarkdownChunker
    embedder: Embedder
    index: VectorIndex

    def index_document(self, doc: Document) -> None:
        chunks = self.chunker.chunk(doc)
        vectors = self.embedder.embed_documents([c.embed_text for c in chunks]) if chunks else []
        self.index.replace(doc, chunks, vectors)
