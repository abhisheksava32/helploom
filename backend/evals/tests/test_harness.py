"""The evaluation harness on the sample knowledge base, run as a regression test.

With the hashing embedder and the extractive provider the evaluation is offline and
deterministic, so these thresholds guard retrieval and answer quality: a change that
makes search or citations worse fails here before it reaches a customer.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.db import transaction

from accounts.models import Organization
from evals.runner import (
    EvalCase,
    format_report,
    kb_files,
    load_cases,
    percentile,
    run,
    sample_knowledge_base,
    sweep_thresholds,
)
from knowledge.embeddings import HashingEmbedder
from knowledge.models import Document

pytestmark = pytest.mark.django_db


def test_cases_cover_every_document_and_out_of_scope_questions() -> None:
    cases = load_cases()
    answerable = [case for case in cases if not case.should_refuse]

    assert len(answerable) >= 25
    assert sum(case.should_refuse for case in cases) >= 5
    assert all(case.key_facts for case in answerable)
    assert {case.expected_document for case in answerable} == {path.name for path in kb_files()}
    assert len({case.id for case in cases}) == len(cases)


def test_the_sample_knowledge_base_uses_every_supported_format() -> None:
    assert {path.suffix for path in kb_files()} == {".md", ".html", ".txt", ".docx", ".pdf"}


def test_case_files_are_validated(tmp_path: Path) -> None:
    broken = tmp_path / "cases.json"
    broken.write_text(
        '{"cases": [{"id": "x", "question": "Both?", "expected_document": "a.md", "should_refuse": true}]}'
    )

    with pytest.raises(ValueError, match="either"):
        load_cases(broken)


def test_retrieval_and_answer_quality_on_the_sample_documents() -> None:
    report = run(sweep=True)

    by_mode = {row.mode: row for row in report.retrieval}
    assert report.embedder == "hashing-v1"
    assert report.documents == 6
    assert by_mode["hybrid"].hit_rate >= 0.95
    assert by_mode["hybrid"].mrr >= 0.9
    assert by_mode["vector"].hit_rate >= 0.9
    assert by_mode["keyword"].hit_rate >= 0.9

    answers = report.answers
    assert answers is not None
    assert answers.citation_accuracy >= 0.9
    assert answers.refusal_accuracy >= 0.9
    assert answers.refusal_recall == 1.0
    assert answers.key_fact_coverage >= 0.6
    assert set(answers.providers) <= {"extractive:extractive-v1", "extractive:relevance-gate"}

    # The shipped default threshold is the one the sweep finds best.
    best = max(row.accuracy for row in report.sweep)
    best_thresholds = [row.threshold for row in report.sweep if row.accuracy == best]
    assert min(best_thresholds) - 0.03 <= HashingEmbedder.default_threshold <= max(best_thresholds) + 0.03

    text = format_report(report, verbose=True)
    assert "hit@5" in text
    assert "Relevance threshold sweep" in text


def test_the_sample_organization_is_rolled_back() -> None:
    with transaction.atomic(), sample_knowledge_base() as kb:
        assert Document.objects.filter(organization_id=kb.organization_id).count() == 6
        organization_id = kb.organization_id

    assert not Organization.objects.filter(pk=organization_id).exists()
    assert not Document.objects.exists()


def test_sweep_reports_one_row_per_step() -> None:
    cases = [
        EvalCase(id="a", question="How long do refunds take?", expected_document="returns-and-refunds.html")
    ]
    with sample_knowledge_base() as kb:
        rows = sweep_thresholds(kb, cases, steps=4)

    assert len(rows) == 5
    assert rows[0].threshold == 0.0
    assert rows[0].answer_rate == 1.0


def test_percentile_uses_nearest_rank() -> None:
    assert percentile([], 0.5) == 0.0
    assert percentile([5, 1, 3], 0.5) == 3
    assert percentile([1, 2, 3, 4], 0.95) == 4
