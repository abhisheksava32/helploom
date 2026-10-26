"""Structure aware chunking: headings, sizes, overlap and offsets."""

from __future__ import annotations

import itertools

from knowledge import extractors
from knowledge.chunking import chunk_extraction, estimate_tokens
from knowledge.extractors import Block, Extraction, extract


def _sentences(count: int, prefix: str = "Sentence") -> str:
    return " ".join(
        f"{prefix} number {index} explains one more detail of the policy." for index in range(count)
    )


def test_chunks_follow_headings_and_carry_the_heading_path() -> None:
    source = "# Returns\n\nIntro.\n\n## Refund window\n\nWithin 30 days.\n\n## Exchanges\n\nFree exchanges."
    chunks = chunk_extraction(extract(source.encode(), extractors.MARKDOWN))

    assert [(c.heading, c.location, c.text) for c in chunks] == [
        ("Returns", "Returns", "Intro."),
        ("Returns > Refund window", "Returns > Refund window", "Within 30 days."),
        ("Returns > Exchanges", "Returns > Exchanges", "Free exchanges."),
    ]
    assert [c.ordinal for c in chunks] == [0, 1, 2]


def test_every_chunk_is_an_exact_slice_of_the_extracted_text() -> None:
    extraction = extract(
        f"# Policy\n\n{_sentences(60)}\n\n## More\n\n{_sentences(5)}".encode(), extractors.MARKDOWN
    )
    full_text = extraction.text

    chunks = chunk_extraction(extraction, target_tokens=80, overlap_tokens=20)

    assert len(chunks) > 3
    for chunk in chunks:
        assert full_text[chunk.char_start : chunk.char_end] == chunk.text


def test_long_sections_are_packed_to_the_target_with_overlap() -> None:
    extraction = Extraction([Block("Policy", heading_level=1), Block(_sentences(40))])

    chunks = chunk_extraction(extraction, target_tokens=60, overlap_tokens=15)

    assert len(chunks) > 1
    assert all(chunk.token_count <= 60 + 15 for chunk in chunks)
    for previous, current in itertools.pairwise(chunks):
        # The next chunk starts before the previous one ends: the overlap.
        assert current.char_start < previous.char_end
        assert current.char_end > previous.char_end


def test_a_single_huge_sentence_is_split_into_word_windows() -> None:
    sentence = " ".join(f"word{index}" for index in range(500))

    chunks = chunk_extraction(Extraction([Block(sentence)]), target_tokens=50, overlap_tokens=0)

    assert len(chunks) >= 10
    assert all(chunk.token_count <= 50 for chunk in chunks)


def test_pdf_chunks_are_located_by_page() -> None:
    extraction = Extraction(
        [
            Block("Rewards", heading_level=2, page_number=1),
            Block("Earn points.", page_number=1),
            Block("Points expire.", page_number=2),
        ],
        page_count=2,
    )

    chunks = chunk_extraction(extraction)

    assert [(c.location, c.page_number, c.heading) for c in chunks] == [
        ("Page 1", 1, "Rewards"),
        ("Page 2", 2, "Rewards"),
    ]


def test_documents_without_headings_get_numbered_sections() -> None:
    chunks = chunk_extraction(Extraction([Block(_sentences(30))]), target_tokens=60, overlap_tokens=0)

    assert [c.location for c in chunks[:2]] == ["Section 1", "Section 2"]
    assert all(c.heading == "" for c in chunks)


def test_token_estimate_counts_words() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("one two three four five six seven eight nine ten") == 13
