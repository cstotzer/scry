from scry.domain import Document, DocumentId, MarkdownChunker, NoteMeta, content_hash


def doc(body: str, title: str = "Guide", summary: str | None = None) -> Document:
    return Document(
        DocumentId("g.md"), NoteMeta(title=title, summary=summary), body, content_hash(body)
    )


def test_splits_by_headings_and_tracks_path() -> None:
    body = "intro\n\n# A\na text\n## B\nb text\n### C\nc text\n## D\nd text\n#### deep\nstill d"
    chunks = MarkdownChunker(1000).chunk(doc(body))
    assert [(c.heading_path, c.text) for c in chunks] == [
        ([], "intro"),
        (["A"], "a text"),
        (["A", "B"], "b text"),
        (["A", "B", "C"], "c text"),
        (["A", "D"], "d text\n#### deep\nstill d"),
    ]
    assert [c.index for c in chunks] == [0, 1, 2, 3, 4]
    assert chunks[3].embed_text == "Guide > A > B > C\n\nc text"


def test_ignores_headings_in_code_fences() -> None:
    body = "# Setup\n```bash\n# not a heading\necho hi\n```\nafter"
    chunks = MarkdownChunker(1000).chunk(doc(body))
    assert len(chunks) == 1
    assert "# not a heading" in chunks[0].text


def test_skips_empty_sections() -> None:
    chunks = MarkdownChunker(1000).chunk(doc("# A\n\n# B\ntext"))
    assert [c.heading_path for c in chunks] == [["B"]]


def test_splits_long_sections_by_paragraph_packing_small_ones() -> None:
    paras = ["a" * 30, "b" * 30, "c" * 30]  # two fit into 70 chars ("\n\n" joined), three don't
    chunks = MarkdownChunker(70).chunk(doc("# Long\n" + "\n\n".join(paras)))
    assert [c.text for c in chunks] == [f"{paras[0]}\n\n{paras[1]}", paras[2]]
    assert all(c.heading_path == ["Long"] for c in chunks)


def test_hard_splits_oversized_paragraph() -> None:
    chunks = MarkdownChunker(10).chunk(doc("x" * 25))
    assert [len(c.text) for c in chunks] == [10, 10, 5]


def test_empty_body_yields_one_chunk_from_summary_or_title() -> None:
    assert MarkdownChunker(100).chunk(doc("", summary="About it"))[0].text == "About it"
    assert MarkdownChunker(100).chunk(doc("  \n", title="Only title"))[0].text == "Only title"


def test_embed_text_drops_obsidian_syntax_but_text_keeps_it() -> None:
    body = "> [!tip] Use [[Proxy Setup|the proxy]] %%todo%% ![[diagram.png]]"
    chunk = MarkdownChunker(1000).chunk(doc(body))[0]
    assert chunk.text == body
    assert chunk.embed_text == "Guide\n\n> Use the proxy  "
