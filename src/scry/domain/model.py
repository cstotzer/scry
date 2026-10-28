import hashlib
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from scry.domain.errors import InvalidDocumentId


@dataclass(frozen=True, order=True)
class DocumentId:
    """Normalized POSIX path of a Markdown file relative to the data dir."""

    value: str

    def __post_init__(self) -> None:
        raw = self.value.strip().replace("\\", "/")
        if not raw or raw.startswith("/"):
            raise InvalidDocumentId(f"invalid document id: {self.value!r}")
        parts = [p for p in raw.split("/") if p not in ("", ".")]
        if not parts or any(p == ".." for p in parts):
            raise InvalidDocumentId(f"invalid document id: {self.value!r}")
        if not parts[-1].endswith(".md") or parts[-1] == ".md":
            raise InvalidDocumentId(f"document id must name a .md file: {self.value!r}")
        object.__setattr__(self, "value", str(PurePosixPath(*parts)))

    def __str__(self) -> str:
        return self.value


class NoteMeta(BaseModel):
    """Note metadata. Title, aliases and summary come from the properties; tags are normalized."""

    model_config = ConfigDict(frozen=True)

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    tags: list[str] = []
    aliases: list[str] = []
    summary: str | None = None

    @field_validator("tags")
    @classmethod
    def _tags_are_normalized(cls, tags: list[str]) -> list[str]:
        for tag in tags:
            if not tag or tag != tag.strip().lower() or " " in tag or tag.startswith("#"):
                raise ValueError(f"tag {tag!r} is not normalized")
        return tags


def content_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Link:
    """A link as written in a note: `[[target#heading|alias]]`, `![[embed]]` or `[x](path.md)`."""

    target: str
    heading: str | None = None
    embed: bool = False


@dataclass(frozen=True)
class Document:
    id: DocumentId
    meta: NoteMeta
    body: str
    content_hash: str
    links: list[Link] = field(default_factory=lambda: list[Link]())
    warnings: list[str] = field(default_factory=lambda: list[str]())


@dataclass(frozen=True)
class Chunk:
    doc_id: DocumentId
    index: int
    heading_path: list[str]
    text: str
    embed_text: str


@dataclass(frozen=True)
class SparseVector:
    indices: list[int]
    values: list[float]


@dataclass(frozen=True)
class Vectors:
    dense: list[float]
    sparse: SparseVector


@dataclass(frozen=True)
class SearchHit:
    doc_id: DocumentId
    title: str
    heading_path: list[str]
    text: str
    score: float


@dataclass(frozen=True)
class FileWarning:
    doc_id: str
    messages: list[str]


@dataclass(frozen=True)
class SyncReport:
    added: list[DocumentId] = field(default_factory=lambda: list[DocumentId]())
    updated: list[DocumentId] = field(default_factory=lambda: list[DocumentId]())
    removed: list[DocumentId] = field(default_factory=lambda: list[DocumentId]())
    warnings: list[FileWarning] = field(default_factory=lambda: list[FileWarning]())


@dataclass(frozen=True)
class IndexStats:
    documents: int
    chunks: int


@dataclass(frozen=True)
class LinkRef:
    """A linked note: how often it is linked, its number of distinct neighbours, hub or not."""

    doc_id: DocumentId
    title: str
    summary: str | None
    mentions: int
    degree: int
    hub: bool


@dataclass(frozen=True)
class NoteLinks:
    outgoing: list[LinkRef]
    backlinks: list[LinkRef]
    total_outgoing: int
    total_backlinks: int
    unresolved: list[str]

    @property
    def truncated(self) -> bool:
        return (
            len(self.outgoing) < self.total_outgoing or len(self.backlinks) < self.total_backlinks
        )
