"""Offline answers built from the retrieved passages, with no model at all.

The sentences of the top passages are scored by lexical overlap with the question
(the same weighted features as the hashing embedder), up to
ASSISTANT_EXTRACTIVE_MAX_SENTENCES are kept, and each carries the marker of the
passage it came from, for example "Refunds are issued within 5 business days [1]."
The output uses the same citation format as the model providers, so citations, the
UI and the evals behave identically offline.
"""

from __future__ import annotations

import math
import re
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass

from django.conf import settings

from knowledge.embeddings import lexical_features, tokenize

from ..prompts import NOT_FOUND_SENTENCE, Prompt
from ..retrieval import Passage
from ..text import split_sentences
from .base import Completed, ProviderEvent, StopReason, TextDelta, Usage

MODEL = "extractive-v1"
# Below this overlap a sentence is not about the question at all.
MIN_SENTENCE_SCORE = 0.06
# Sentences far weaker than the best match are padding, not support.
RELATIVE_SCORE_CUTOFF = 0.45
# Lower ranked passages are slightly less trusted than the best ones.
RANK_DECAY = 0.04
_LIST_PREFIX = re.compile(r"^(?:[-*+\u2022]|\d{1,3}[.)])\s+")


@dataclass(frozen=True)
class _Candidate:
    score: float
    passage_index: int
    position: int
    text: str


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    dot = sum(weight * right.get(feature, 0.0) for feature, weight in left.items())
    norm = math.sqrt(sum(w * w for w in left.values())) * math.sqrt(sum(w * w for w in right.values()))
    return dot / norm if norm else 0.0


def _clean(sentence: str) -> str:
    return _LIST_PREFIX.sub("", sentence).strip()


def _with_marker(sentence: str, marker: int) -> str:
    if sentence[-1] in ".!?":
        return f"{sentence[:-1]} [{marker}]{sentence[-1]}"
    return f"{sentence.rstrip(':;,')} [{marker}]."


def compose_answer(question: str, passages: Sequence[Passage], max_sentences: int | None = None) -> str:
    limit = max_sentences or settings.ASSISTANT_EXTRACTIVE_MAX_SENTENCES
    query = lexical_features(question)
    candidates: list[_Candidate] = []
    for passage_index, passage in enumerate(passages):
        for position, sentence in enumerate(split_sentences(passage.text)):
            text = _clean(sentence)
            if len(tokenize(text)) < 3:
                continue
            score = _cosine(query, lexical_features(text)) * (1.0 - RANK_DECAY * passage_index)
            if score >= MIN_SENTENCE_SCORE:
                candidates.append(_Candidate(score, passage_index, position, text))

    chosen: list[_Candidate] = []
    seen: set[str] = set()
    best = max((c.score for c in candidates), default=0.0)
    for candidate in sorted(candidates, key=lambda c: -c.score):
        if candidate.score < best * RELATIVE_SCORE_CUTOFF:
            break
        key = " ".join(tokenize(candidate.text))
        if key in seen:
            continue  # the same sentence repeated in two documents
        seen.add(key)
        chosen.append(candidate)
        if len(chosen) == limit:
            break
    if not chosen:
        return NOT_FOUND_SENTENCE
    chosen.sort(key=lambda c: (c.passage_index, c.position))
    return " ".join(_with_marker(c.text, c.passage_index + 1) for c in chosen)


class ExtractiveProvider:
    name = "extractive"
    model = MODEL

    async def is_available(self) -> bool:
        return True

    async def stream(self, prompt: Prompt) -> AsyncGenerator[ProviderEvent]:
        answer = compose_answer(prompt.question, prompt.passages)
        sentences = re.split(r"(?<=[.!?]) (?=\S)", answer)
        # Sentence by sentence, so the UI streams the same way as with a model.
        for index, sentence in enumerate(sentences):
            yield TextDelta(sentence if index == len(sentences) - 1 else f"{sentence} ")
        yield Completed(stop_reason=StopReason.END_TURN, model=self.model, usage=Usage(), text=answer)
