import posixpath
from collections import Counter
from collections.abc import Iterable, Mapping

from scry.domain.model import DocumentId, Link

# Embeds of these are attachments, not notes; any other suffix ("v1.2 notes") is part of a name.
ATTACHMENT_SUFFIXES = frozenset(
    [
        "avif",
        "bmp",
        "gif",
        "jpeg",
        "jpg",
        "png",
        "svg",
        "webp",
        "mp3",
        "m4a",
        "ogg",
        "wav",
        "flac",
        "webm",
        "mp4",
        "mov",
        "mkv",
        "pdf",
        "canvas",
        "base",
        "excalidraw",
    ]
)


def _key(path: str) -> str:
    return path.lower().removesuffix(".md")


class LinkResolver:
    """Resolves link targets to notes like Obsidian: by path when given, else by file name."""

    def __init__(self, ids: Iterable[DocumentId]) -> None:
        self._by_path: dict[str, DocumentId] = {}
        self._by_name: dict[str, list[DocumentId]] = {}
        for doc_id in sorted(ids, key=lambda d: (d.value.count("/"), d.value)):
            self._by_path[_key(doc_id.value)] = doc_id
            self._by_name.setdefault(_key(posixpath.basename(doc_id.value)), []).append(doc_id)

    def resolve(self, link: Link, source: DocumentId) -> DocumentId | None:
        target = link.target.strip().replace("\\", "/")
        suffix = posixpath.splitext(target)[1].lower().lstrip(".")
        if suffix in ATTACHMENT_SUFFIXES:
            return None
        if "/" not in target:
            matches = self._by_name.get(_key(target))
            return matches[0] if matches else None  # shortest path wins, like Obsidian
        relative = posixpath.normpath(posixpath.join(posixpath.dirname(source.value), target))
        for candidate in (relative, posixpath.normpath(target.lstrip("/"))):
            if (found := self._by_path.get(_key(candidate))) is not None:
                return found
        tail = "/" + _key(target.lstrip("./"))  # a partial path, e.g. "Projects/Plan"
        matches = [d for k, d in self._by_path.items() if ("/" + k).endswith(tail)]
        return matches[0] if matches else None


class LinkGraph:
    """Resolved links between notes. Notes with at least `hub_degree` neighbours are hubs."""

    def __init__(
        self,
        outgoing: Mapping[DocumentId, Counter[DocumentId]],
        unresolved: Mapping[DocumentId, list[str]],
        hub_degree: int,
    ) -> None:
        self._outgoing = dict(outgoing)
        self._unresolved = dict(unresolved)
        self._backlinks: dict[DocumentId, Counter[DocumentId]] = {}
        for source, targets in self._outgoing.items():
            for target, n in targets.items():
                self._backlinks.setdefault(target, Counter())[source] += n
        self._hub_degree = hub_degree

    @classmethod
    def build(
        cls, links: Mapping[DocumentId, list[Link]], resolver: LinkResolver, hub_degree: int
    ) -> "LinkGraph":
        outgoing: dict[DocumentId, Counter[DocumentId]] = {}
        unresolved: dict[DocumentId, list[str]] = {}
        for source, doc_links in links.items():
            for link in doc_links:
                target = resolver.resolve(link, source)
                if target is None:
                    if not link.embed and link.target not in unresolved.get(source, []):
                        unresolved.setdefault(source, []).append(link.target)
                elif target != source:
                    outgoing.setdefault(source, Counter())[target] += 1
        return cls(outgoing, unresolved, hub_degree)

    @classmethod
    def empty(cls) -> "LinkGraph":
        return cls({}, {}, 1)

    def outgoing(self, doc_id: DocumentId) -> Counter[DocumentId]:
        return Counter(self._outgoing.get(doc_id, {}))

    def backlinks(self, doc_id: DocumentId) -> Counter[DocumentId]:
        return Counter(self._backlinks.get(doc_id, {}))

    def unresolved(self, doc_id: DocumentId) -> list[str]:
        return list(self._unresolved.get(doc_id, []))

    def degree(self, doc_id: DocumentId) -> int:
        return len(set(self._outgoing.get(doc_id, ())) | set(self._backlinks.get(doc_id, ())))

    def is_hub(self, doc_id: DocumentId) -> bool:
        return self.degree(doc_id) >= self._hub_degree

    def rank(self, linked: Counter[DocumentId]) -> list[DocumentId]:
        """Specific notes first: non-hubs, then more mentions, then fewer neighbours."""
        return sorted(linked, key=lambda d: (self.is_hub(d), -linked[d], self.degree(d), d.value))
