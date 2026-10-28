import pytest
from pydantic import ValidationError

from scry.domain import DocumentId, InvalidDocumentId, NoteMeta


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ops/proxy-setup.md", "ops/proxy-setup.md"),
        ("./ops//proxy-setup.md", "ops/proxy-setup.md"),
        ("ops\\proxy.md", "ops/proxy.md"),
        (" note.md ", "note.md"),
    ],
)
def test_document_id_normalizes(raw: str, expected: str) -> None:
    assert DocumentId(raw).value == expected


@pytest.mark.parametrize(
    "raw", ["", "/etc/passwd.md", "../x.md", "a/../../x.md", "notes.txt", "dir/", ".md"]
)
def test_document_id_rejects(raw: str) -> None:
    with pytest.raises(InvalidDocumentId):
        DocumentId(raw)


def test_document_ids_compare_by_value() -> None:
    assert DocumentId("./a.md") == DocumentId("a.md")
    assert sorted([DocumentId("b.md"), DocumentId("a.md")])[0].value == "a.md"


def test_note_meta_requires_title_and_normalized_tags() -> None:
    meta = NoteMeta(title=" Proxy ", tags=["network", "project/work"])
    assert meta.title == "Proxy"
    assert meta.summary is None
    for bad in (
        {"title": "  "},
        {"title": "x", "tags": ["Network"]},
        {"title": "x", "tags": ["#a"]},
    ):
        with pytest.raises(ValidationError):
            NoteMeta.model_validate(bad)
