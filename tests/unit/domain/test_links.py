from collections import Counter

from scry.domain import DocumentId, Link, LinkGraph, LinkResolver

IDS = [
    DocumentId(p)
    for p in ["Proxy.md", "deep/dir/Proxy.md", "ops/Docker.md", "ops/sub/Plan.md", "v1.2 notes.md"]
]


def resolve(target: str, source: str = "x.md") -> str | None:
    found = LinkResolver(IDS).resolve(Link(target), DocumentId(source))
    return found.value if found else None


def test_resolves_names_case_insensitively_preferring_the_shortest_path() -> None:
    assert resolve("proxy") == "Proxy.md"
    assert resolve("Docker.md") == "ops/Docker.md"
    assert resolve("v1.2 notes") == "v1.2 notes.md"


def test_resolves_paths_relative_absolute_and_partial() -> None:
    assert resolve("deep/dir/Proxy") == "deep/dir/Proxy.md"
    assert resolve("sub/Plan.md", source="ops/Docker.md") == "ops/sub/Plan.md"
    assert resolve("../Docker", source="ops/sub/Plan.md") == "ops/Docker.md"
    assert resolve("dir/Proxy") == "deep/dir/Proxy.md"


def test_unresolved_targets_and_attachments() -> None:
    assert resolve("Missing") is None
    assert resolve("Proxy.png") is None
    assert resolve("nope/Proxy") is None


def graph(edges: dict[str, list[str]], hub_degree: int = 3) -> LinkGraph:
    links = {DocumentId(s): [Link(t) for t in ts] for s, ts in edges.items()}
    return LinkGraph.build(links, LinkResolver(links), hub_degree)


def test_graph_counts_mentions_backlinks_and_unresolved() -> None:
    g = graph({"a.md": ["b", "b", "c", "a", "ghost", "ghost"], "b.md": ["a"], "c.md": []})
    a, b, c = DocumentId("a.md"), DocumentId("b.md"), DocumentId("c.md")
    assert g.outgoing(a) == Counter({b: 2, c: 1})  # self-link dropped
    assert g.backlinks(a) == Counter({b: 1})
    assert g.unresolved(a) == ["ghost"]
    assert g.degree(a) == 2 and g.degree(c) == 1


def test_rank_puts_specific_notes_before_hubs() -> None:
    g = graph(
        {
            "src.md": ["hub", "rare", "often", "often"],
            "hub.md": ["x", "y", "z"],
            "x.md": [],
            "y.md": [],
            "z.md": [],
            "rare.md": [],
            "often.md": ["x"],
        }
    )
    order = g.rank(g.outgoing(DocumentId("src.md")))
    assert [d.value for d in order] == ["often.md", "rare.md", "hub.md"]
    assert g.is_hub(DocumentId("hub.md"))
