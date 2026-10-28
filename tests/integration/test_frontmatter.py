import pytest

from scry.adapters.frontmatter import FrontMatterParser
from scry.domain import DocumentId, Link, content_hash

ID = DocumentId("ops/Proxy Setup.md")


def test_parses_properties_tags_aliases_and_links() -> None:
    raw = (
        "---\ntitle: Proxy\ntags: [Network, ops/proxy]\naliases: [squid]\n"
        "description: How to.\ncreated: 2024-01-01\ncssclasses: wide\n---\n"
        "# Body\ntext #inline see [[Docker]]\n"
    )
    doc = FrontMatterParser().parse(ID, raw)
    assert doc.meta.title == "Proxy"
    assert doc.meta.tags == ["network", "ops", "ops/proxy", "inline"]
    assert doc.meta.aliases == ["squid"]
    assert doc.meta.summary == "How to."
    assert doc.body.startswith("# Body")
    assert doc.links == [Link("Docker")]
    assert doc.warnings == []
    assert doc.content_hash == content_hash(raw)


@pytest.mark.parametrize(
    "raw",
    ["# no properties\ntext", "---\n---\ntext", "﻿# bom\ntext", "---\r\ntags: a, b\r\n---\r\ntext"],
)
def test_title_falls_back_to_the_file_name(raw: str) -> None:
    doc = FrontMatterParser().parse(ID, raw)
    assert doc.meta.title == "Proxy Setup"
    assert doc.warnings == []
    assert "text" in doc.body


def test_tags_as_a_string() -> None:
    doc = FrontMatterParser().parse(ID, "---\ntags: a, B c\n---\n")
    assert doc.meta.tags == ["a", "b", "c"]


@pytest.mark.parametrize("props", ["title: [unclosed", "- just\n- a list"])
def test_unusable_properties_become_a_warning(props: str) -> None:
    doc = FrontMatterParser().parse(ID, f"---\n{props}\n---\nbody text")
    assert doc.meta.title == "Proxy Setup"
    assert doc.body == "body text"
    assert len(doc.warnings) == 1
