"""Turn [n] markers in an answer back into structured citations.

The model (or the extractive provider) cites passages by the numbers it saw. Markers
that point at no passage are removed from the stored text, grouped markers such as
[1, 3] are rewritten as [1][3] so every client renders one chip per source, and each
distinct valid marker becomes a citation carrying copies of the passage's title,
location and snippet.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from .retrieval import Passage
from .text import shorten

SNIPPET_MAX_CHARS = 300
_MARKER_GROUP = re.compile(r"(\s*)\[(\s*\d{1,3}(?:\s*,\s*\d{1,3})*\s*)\]")


@dataclass(frozen=True)
class CitationRef:
    marker: int
    passage: Passage

    @property
    def snippet(self) -> str:
        return shorten(self.passage.text, SNIPPET_MAX_CHARS)

    def as_frame(self) -> dict[str, object]:
        similarity = self.passage.similarity
        return {
            "marker": self.marker,
            "document_id": str(self.passage.document_id),
            "chunk_id": str(self.passage.chunk_id),
            "document_title": self.passage.document_title,
            "location": self.passage.location,
            "snippet": self.snippet,
            "score": round(similarity, 4) if similarity is not None else None,
        }


def parse_citations(text: str, passages: Sequence[Passage]) -> tuple[str, list[CitationRef]]:
    """Return the cleaned answer text and its citations ordered by marker."""
    cited: dict[int, CitationRef] = {}

    def replace(match: re.Match[str]) -> str:
        numbers = [int(part) for part in match.group(2).split(",")]
        valid: list[int] = []
        for number in numbers:
            if 1 <= number <= len(passages) and number not in valid:
                valid.append(number)
                cited.setdefault(number, CitationRef(marker=number, passage=passages[number - 1]))
        if not valid:
            # The match includes the whitespace before the marker, so "word [9]."
            # becomes "word." rather than "word .".
            return ""
        return match.group(1) + "".join(f"[{number}]" for number in valid)

    cleaned = _MARKER_GROUP.sub(replace, text).strip()
    return cleaned, [cited[number] for number in sorted(cited)]
