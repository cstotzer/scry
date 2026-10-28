from typing import Protocol

from scry.domain import Vectors


class Embedder(Protocol):
    @property
    def dense_dim(self) -> int: ...
    def embed_documents(self, texts: list[str]) -> list[Vectors]: ...
    def embed_query(self, text: str) -> Vectors: ...
