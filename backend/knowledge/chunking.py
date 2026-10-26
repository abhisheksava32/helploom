"""Split extracted blocks into retrievable passages.

Structure first, size second: the text is cut at headings, then paragraphs and
sentences are packed up to CHUNK_TARGET_TOKENS with CHUNK_OVERLAP_TOKENS of overlap
inside a section. Keeping a policy section in one chunk (or a few overlapping ones)
means a retrieved passage carries its own context, and its heading path makes a
readable citation ("Returns > Refund window").

Every chunk's text is an exact slice of Document.extracted_text (char_start to
char_end), so the preview can highlight what an answer cited.

Token counts are estimated from words (about 1.3 tokens per English word). That is
accurate enough for packing and needs no tokenizer download.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from django.conf import settings

from .extractors import Extraction, join_blocks

TOKENS_PER_WORD = 1.3
HEADING_SEPARATOR = " > "
_WORD = re.compile(r"\S+")
# A sentence ends at . ! or ? followed by whitespace; a line break also ends a unit so
# list items and table rows stay whole.
_SENTENCE = re.compile(r"[^\n]*?[.!?](?=\s)|[^\n]+")


def estimate_tokens(text: str) -> int:
    words = len(_WORD.findall(text))
    return math.ceil(words * TOKENS_PER_WORD) if words else 0


@dataclass(frozen=True)
class ChunkDraft:
    ordinal: int
    text: str
    heading: str
    location: str
    page_number: int | None
    char_start: int
    char_end: int
    token_count: int


@dataclass(frozen=True)
class _Unit:
    start: int
    end: int
    tokens: int


@dataclass
class _Section:
    path: tuple[str, ...]
    page_number: int | None
    units: list[_Unit] = field(default_factory=list)


def _trimmed(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _word_windows(text: str, start: int, end: int, target: int) -> Iterator[_Unit]:
    """Last resort for a single sentence longer than a whole chunk."""
    words_per_window = max(1, int(target / TOKENS_PER_WORD))
    words = list(_WORD.finditer(text, start, end))
    for index in range(0, len(words), words_per_window):
        window = words[index : index + words_per_window]
        yield _Unit(window[0].start(), window[-1].end(), math.ceil(len(window) * TOKENS_PER_WORD))


def _units(text: str, start: int, end: int, target: int) -> Iterator[_Unit]:
    tokens = estimate_tokens(text[start:end])
    if tokens <= target:
        if tokens:
            yield _Unit(start, end, tokens)
        return
    for match in _SENTENCE.finditer(text, start, end):
        s_start, s_end = _trimmed(text, match.start(), match.end())
        sentence_tokens = estimate_tokens(text[s_start:s_end])
        if not sentence_tokens:
            continue
        if sentence_tokens <= target:
            yield _Unit(s_start, s_end, sentence_tokens)
        else:
            yield from _word_windows(text, s_start, s_end, target)


def _sections(extraction: Extraction, full_text: str, offsets: list[int], target: int) -> list[_Section]:
    sections: list[_Section] = []
    stack: list[tuple[int, str]] = []
    current: _Section | None = None
    for block, start in zip(extraction.blocks, offsets, strict=True):
        if block.is_heading:
            while stack and stack[-1][0] >= block.heading_level:
                stack.pop()
            stack.append((block.heading_level, block.text))
            current = None
            continue
        path = tuple(text for _, text in stack)
        # A page break starts a new section too, so every chunk has one page number.
        if current is None or current.path != path or current.page_number != block.page_number:
            current = _Section(path=path, page_number=block.page_number)
            sections.append(current)
        current.units.extend(_units(full_text, start, start + len(block.text), target))
    return [section for section in sections if section.units]


def _pack(units: list[_Unit], target: int, overlap: int) -> Iterator[list[_Unit]]:
    current: list[_Unit] = []
    tokens = 0
    for unit in units:
        if current and tokens + unit.tokens > target:
            yield current
            # Carry the tail of the previous chunk forward so a fact that straddles
            # the cut is still whole in one of the two chunks.
            tail: list[_Unit] = []
            tail_tokens = 0
            for previous in reversed(current):
                if tail_tokens + previous.tokens > overlap:
                    break
                tail.insert(0, previous)
                tail_tokens += previous.tokens
            while tail and tail_tokens + unit.tokens > target:
                tail_tokens -= tail.pop(0).tokens
            current, tokens = tail, tail_tokens
        current.append(unit)
        tokens += unit.tokens
    if current:
        yield current


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def chunk_extraction(
    extraction: Extraction, target_tokens: int | None = None, overlap_tokens: int | None = None
) -> list[ChunkDraft]:
    target = target_tokens or settings.CHUNK_TARGET_TOKENS
    overlap = settings.CHUNK_OVERLAP_TOKENS if overlap_tokens is None else overlap_tokens
    overlap = min(overlap, target // 2)
    full_text, offsets = join_blocks(extraction.blocks)

    drafts: list[ChunkDraft] = []
    for section in _sections(extraction, full_text, offsets, target):
        heading = _shorten(HEADING_SEPARATOR.join(section.path), 255)
        for units in _pack(section.units, target, overlap):
            start, end = units[0].start, units[-1].end
            text = full_text[start:end]
            ordinal = len(drafts)
            if section.page_number is not None:
                location = f"Page {section.page_number}"
            elif heading:
                location = _shorten(heading, 120)
            else:
                location = f"Section {ordinal + 1}"
            drafts.append(
                ChunkDraft(
                    ordinal=ordinal,
                    text=text,
                    heading=heading,
                    location=location,
                    page_number=section.page_number,
                    char_start=start,
                    char_end=end,
                    token_count=estimate_tokens(text),
                )
            )
    return drafts
