from collections.abc import Callable
from dataclasses import dataclass

from scry.app.get_document import GetDocument
from scry.app.get_links import GetLinks
from scry.app.list_documents import ListDocuments
from scry.app.search import Search
from scry.app.sync_index import SyncIndex
from scry.domain import IndexStats


@dataclass(frozen=True)
class Services:
    """The use cases, bundled for the inbound adapters."""

    sync: SyncIndex
    search: Search
    get: GetDocument
    links: GetLinks
    list_documents: ListDocuments
    stats: Callable[[], IndexStats]
