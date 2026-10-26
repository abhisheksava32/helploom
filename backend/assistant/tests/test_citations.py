"""Turning [n] markers back into structured citations."""

from __future__ import annotations

import uuid

from assistant.citations import SNIPPET_MAX_CHARS, parse_citations
from assistant.retrieval import Passage


def passages(count: int) -> list[Passage]:
    return [
        Passage(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_title=f"Doc {n}",
            location=f"Section {n}",
            heading="",
            text=f"Passage {n} text. " * 40,
            similarity=0.5 + n / 100 if n != 3 else None,
        )
        for n in range(1, count + 1)
    ]


def test_valid_markers_become_citations_and_invalid_ones_disappear() -> None:
    sources = passages(3)

    text, citations = parse_citations(
        "Refunds take 5 days [1]. Exchanges are free [2, 3]. Fake [9].", sources
    )

    assert text == "Refunds take 5 days [1]. Exchanges are free [2][3]. Fake."
    assert [c.marker for c in citations] == [1, 2, 3]
    assert [c.passage for c in citations] == sources


def test_markers_keep_the_numbers_the_model_saw() -> None:
    sources = passages(3)

    text, citations = parse_citations("Only the third [3] and the first [1] [1].", sources)

    assert text == "Only the third [3] and the first [1] [1]."
    assert [c.marker for c in citations] == [1, 3]


def test_text_without_markers_has_no_citations() -> None:
    assert parse_citations("No sources here.", passages(2)) == ("No sources here.", [])


def test_citation_frames_copy_passage_details() -> None:
    sources = passages(3)
    _, citations = parse_citations("A [1]. C [3].", sources)

    first, third = (citation.as_frame() for citation in citations)

    assert first["document_id"] == str(sources[0].document_id)
    assert first["chunk_id"] == str(sources[0].chunk_id)
    assert first["document_title"] == "Doc 1"
    assert first["score"] == 0.51
    assert len(str(first["snippet"])) <= SNIPPET_MAX_CHARS
    assert str(first["snippet"]).endswith("...")
    assert third["score"] is None  # a keyword only match has no similarity
