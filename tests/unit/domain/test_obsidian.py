from scry.domain import (
    Link,
    clean_for_embedding,
    extract_inline_tags,
    extract_links,
    normalize_tags,
    replace_wikilinks,
)


def test_extracts_every_link_form_in_order() -> None:
    body = (
        "See [[Proxy]], [[Docker#Daemon config|daemon]] and [[Notes#^block1]].\n"
        "![[diagram.png]] ![[Other note]]\n"
        "| [[Table\\|alias]] |\n"
        "[md](sub/My%20Note.md#Part) [angle](<With Space.md>) [web](https://x.org/a.md)"
    )
    assert extract_links(body) == [
        Link("Proxy"),
        Link("Docker", "Daemon config"),
        Link("Notes", "^block1"),
        Link("diagram.png", embed=True),
        Link("Other note", embed=True),
        Link("Table"),
        Link("sub/My Note.md", "Part"),
        Link("With Space.md"),
    ]


def test_ignores_links_in_code_and_comments_and_self_links() -> None:
    body = "`[[inline]]`\n```\n[[fenced]]\n```\n%%[[hidden]]%%\n[[#Heading]] [[real]]"
    assert extract_links(body) == [Link("real")]


def test_inline_tags() -> None:
    body = "# Heading\n#idea and #Project/Work, not #123 or a#b or `#code`\n```\n#x\n```"
    assert extract_inline_tags(body) == ["idea", "Project/Work"]


def test_normalize_tags_adds_parents_and_dedupes() -> None:
    assert normalize_tags(["#Project/Work", "project", "Two Words", "#"]) == [
        "project",
        "project/work",
        "two-words",
    ]


def test_clean_for_embedding() -> None:
    text = "> [!warning]- Careful\n> see [[A|alias]], [[B]], [[C#Part]] %%x%% ![[img.png]]"
    assert clean_for_embedding(text) == "> Careful\n> see alias, B, C  "


def test_replace_wikilinks_leaves_code_alone() -> None:
    body = "[[A]] `[[B]]` [[C#H|c]] [[D#H]]"
    rendered = replace_wikilinks(body, lambda link, text: f"<{link.target}:{text}>")
    assert rendered == "<A:A> `[[B]]` <C:c> <D:D > H>"


def test_replace_wikilinks_passes_same_note_headings_with_empty_target() -> None:
    rendered = replace_wikilinks(
        "[[#Setup]] [[#Setup|go]] [[]]", lambda link, text: f"<{link.target}#{link.heading}:{text}>"
    )
    assert rendered == "<#Setup:Setup> <#Setup:go> [[]]"
