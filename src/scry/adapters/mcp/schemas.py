from pydantic import BaseModel


class SearchResult(BaseModel):
    doc_id: str
    url: str
    title: str
    heading_path: list[str]
    text: str
    score: float


class DocumentContent(BaseModel):
    doc_id: str
    url: str
    title: str
    tags: list[str]
    aliases: list[str]
    summary: str | None
    body: str
    outgoing_links: int
    backlinks: int


class LinkedNote(BaseModel):
    doc_id: str
    url: str
    title: str
    summary: str | None
    mentions: int
    hub: bool


class NoteLinksResult(BaseModel):
    outgoing: list[LinkedNote]
    backlinks: list[LinkedNote]
    total_outgoing: int
    total_backlinks: int
    truncated: bool
    unresolved: list[str]


class DocumentListing(BaseModel):
    doc_id: str
    url: str
    title: str
    tags: list[str]
    summary: str | None


class ReindexResult(BaseModel):
    added: list[str]
    updated: list[str]
    removed: list[str]
    warnings: dict[str, list[str]]
