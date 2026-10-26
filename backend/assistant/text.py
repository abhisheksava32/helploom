"""Small text helpers shared by the answer pipeline and the views."""

from __future__ import annotations

import re
import unicodedata

_NOT_WORD = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE = re.compile(r"\s+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])")

NORMALIZED_MAX_CHARS = 300
TITLE_MAX_CHARS = 120


def normalize_question(text: str) -> str:
    """Lower case, punctuation stripped, whitespace collapsed: the grouping key for the
    top questions report, so "How long do refunds take?" and "how long do refunds
    take" count as one question."""
    folded = unicodedata.normalize("NFKC", text).lower()
    folded = _NOT_WORD.sub(" ", folded).replace("_", " ")
    return _SPACE.sub(" ", folded).strip()[:NORMALIZED_MAX_CHARS]


def shorten(text: str, limit: int) -> str:
    """Cut at a word boundary and mark the cut, for titles and snippets."""
    text = _SPACE.sub(" ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 3]
    if " " in cut[limit // 2 :]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:.") + "..."


def conversation_title(question: str) -> str:
    return shorten(question, TITLE_MAX_CHARS)


def split_sentences(text: str) -> list[str]:
    """Split on sentence punctuation and line breaks; good enough for policy prose."""
    sentences: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if line:
            sentences.extend(part.strip() for part in _SENTENCE.split(line) if part.strip())
    return sentences
