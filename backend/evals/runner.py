"""Retrieval and answer evaluation over the sample knowledge base.

The harness ingests evals/kb/ into a throwaway organisation through the real upload
and ingestion code, then measures:

- hit rate at k: share of answerable questions whose expected document is among the
  top k passages;
- MRR: mean reciprocal rank of the first passage from the expected document;
- citation accuracy: share of answerable questions whose answer cites the expected
  document;
- key fact coverage: share of expected facts that appear in the answers;
- refusal accuracy: share of all questions handled correctly, meaning should refuse
  questions get the not found answer and answerable ones do not;
- latency: retrieval and answer p50 and p95.

Retrieval can be measured vector only, keyword only and hybrid, and the relevance
threshold can be swept, which is how each embedder's default threshold is chosen.
Everything runs inside one rolled back transaction with a temporary MEDIA_ROOT, so a
run leaves nothing behind. With the hashing embedder and the extractive provider it
is fully offline and deterministic, which is why the test suite runs it too.
"""

from __future__ import annotations

import json
import math
import tempfile
import time
import uuid
from collections import Counter
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from asgiref.sync import async_to_sync
from django.conf import settings
from django.db import transaction
from django.test import override_settings

from assistant.models import AnswerType
from assistant.retrieval import Mode, search
from assistant.services import AnswerOutcome, generate_answer, resolve_outcome

EVALS_DIR = Path(__file__).resolve().parent
KB_DIR = EVALS_DIR / "kb"
CASES_PATH = EVALS_DIR / "cases.json"
COMPANY = "Kettlewick Coffee Co."
MODES: tuple[Mode, ...] = ("vector", "keyword", "hybrid")


@dataclass(frozen=True)
class EvalCase:
    id: str
    question: str
    expected_document: str | None = None
    key_facts: tuple[str, ...] = ()
    should_refuse: bool = False


def load_cases(path: Path = CASES_PATH) -> list[EvalCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    cases = [
        EvalCase(
            id=item["id"],
            question=item["question"],
            expected_document=item.get("expected_document"),
            key_facts=tuple(item.get("key_facts", ())),
            should_refuse=bool(item.get("should_refuse", False)),
        )
        for item in raw["cases"]
    ]
    for case in cases:
        if case.should_refuse == bool(case.expected_document):
            raise ValueError(f"Case {case.id} needs either expected_document or should_refuse.")
    return cases


def kb_files(directory: Path = KB_DIR) -> list[Path]:
    allowed = {f".{extension}" for extension in settings.ALLOWED_DOCUMENT_TYPES}
    return sorted(path for path in directory.iterdir() if path.suffix.lower() in allowed)


def percentile(values: Sequence[float], share: float) -> float:
    """Nearest rank percentile; 0 for an empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(share * len(ordered)) - 1)
    return float(ordered[index])


# Sample organisation


@dataclass
class SampleKnowledgeBase:
    organization: Any
    documents: dict[str, uuid.UUID]  # filename -> document id

    @property
    def organization_id(self) -> uuid.UUID:
        return self.organization.pk


def ingest_kb(organization: Any, files: Sequence[Path] | None = None) -> dict[str, uuid.UUID]:
    from knowledge.models import DocumentStatus
    from knowledge.services import create_document, ingest_document

    documents: dict[str, uuid.UUID] = {}
    for path in files or kb_files():
        document = create_document(organization, filename=path.name, data=path.read_bytes())
        ingest_document(document.pk)
        document.refresh_from_db()
        if document.status != DocumentStatus.READY:
            raise RuntimeError(f"{path.name} did not ingest: {document.error_message}")
        documents[path.name] = document.pk
    return documents


@contextmanager
def sample_knowledge_base(tone: str = "friendly") -> Iterator[SampleKnowledgeBase]:
    from accounts.models import Organization

    with (
        tempfile.TemporaryDirectory(prefix="helploom-evals-") as media_root,
        override_settings(MEDIA_ROOT=media_root),
        transaction.atomic(),
    ):
        organization = Organization.objects.create(
            name=COMPANY, slug=f"evals-{uuid.uuid4().hex[:12]}", assistant_tone=tone
        )
        try:
            yield SampleKnowledgeBase(organization=organization, documents=ingest_kb(organization))
        finally:
            transaction.set_rollback(True)


# Retrieval


@dataclass
class RetrievalCaseResult:
    case_id: str
    rank: int | None
    top_similarity: float | None
    latency_ms: float


@dataclass
class RetrievalReport:
    mode: str
    k: int
    hit_rate_at: dict[int, float]
    mrr: float
    latency_p50_ms: float
    latency_p95_ms: float
    cases: list[RetrievalCaseResult] = field(default_factory=list)

    @property
    def hit_rate(self) -> float:
        return self.hit_rate_at[self.k]


def evaluate_retrieval(
    kb: SampleKnowledgeBase, cases: Sequence[EvalCase], *, mode: Mode = "hybrid", k: int = 5, depth: int = 10
) -> RetrievalReport:
    answerable = [case for case in cases if not case.should_refuse]
    results: list[RetrievalCaseResult] = []
    for case in answerable:
        started = time.perf_counter()
        result = search(kb.organization_id, case.question, top_k=max(depth, k), mode=mode)
        elapsed = (time.perf_counter() - started) * 1000
        expected = kb.documents.get(case.expected_document or "")
        rank = next(
            (
                index
                for index, passage in enumerate(result.passages, start=1)
                if passage.document_id == expected
            ),
            None,
        )
        results.append(RetrievalCaseResult(case.id, rank, result.top_similarity, elapsed))

    total = max(1, len(results))
    cutoffs = sorted({1, 3, k})
    hit_rate_at = {
        cut: sum(1 for r in results if r.rank is not None and r.rank <= cut) / total for cut in cutoffs
    }
    latencies = [r.latency_ms for r in results]
    return RetrievalReport(
        mode=mode,
        k=k,
        hit_rate_at=hit_rate_at,
        mrr=sum(1.0 / r.rank for r in results if r.rank) / total,
        latency_p50_ms=percentile(latencies, 0.5),
        latency_p95_ms=percentile(latencies, 0.95),
        cases=results,
    )


# Answers


@dataclass
class AnswerCaseResult:
    case_id: str
    should_refuse: bool
    answer_type: str
    content: str
    provider: str
    model: str
    cited_expected: bool | None
    facts_found: int
    facts_total: int
    top_similarity: float | None
    retrieval_ms: float
    answer_ms: float

    @property
    def handled_correctly(self) -> bool:
        refused = self.answer_type == AnswerType.NOT_FOUND
        return refused if self.should_refuse else not refused


@dataclass
class AnswerReport:
    citation_accuracy: float
    key_fact_coverage: float
    refusal_accuracy: float
    refusal_recall: float
    false_refusal_rate: float
    retrieval_p50_ms: float
    retrieval_p95_ms: float
    answer_p50_ms: float
    answer_p95_ms: float
    providers: dict[str, int]
    cases: list[AnswerCaseResult] = field(default_factory=list)


async def _drain(deltas: AsyncIterator[str]) -> None:
    async for _ in deltas:
        pass


def _answer_case(kb: SampleKnowledgeBase, case: EvalCase) -> AnswerCaseResult:
    organization = kb.organization
    started = time.perf_counter()
    retrieval = search(kb.organization_id, case.question)
    retrieval_ms = (time.perf_counter() - started) * 1000

    outcome = AnswerOutcome()
    generation_started = time.monotonic()
    async_to_sync(_drain)(
        generate_answer(
            organization_id=kb.organization_id,
            business_name=organization.name,
            tone=organization.assistant_tone,
            question=case.question,
            outcome=outcome,
            started=generation_started,
            retrieval=retrieval,
        )
    )
    resolve_outcome(outcome, organization.assistant_tone)
    answer_ms = (time.perf_counter() - started) * 1000

    expected = kb.documents.get(case.expected_document or "")
    cited = (
        None if case.should_refuse else any(ref.passage.document_id == expected for ref in outcome.citations)
    )
    content = outcome.content.lower()
    found = sum(1 for fact in case.key_facts if fact.lower() in content)
    return AnswerCaseResult(
        case_id=case.id,
        should_refuse=case.should_refuse,
        answer_type=outcome.answer_type,
        content=outcome.content,
        provider=outcome.provider,
        model=outcome.model,
        cited_expected=cited,
        facts_found=found,
        facts_total=len(case.key_facts),
        top_similarity=retrieval.top_similarity,
        retrieval_ms=retrieval_ms,
        answer_ms=answer_ms,
    )


def evaluate_answers(kb: SampleKnowledgeBase, cases: Sequence[EvalCase]) -> AnswerReport:
    results = [_answer_case(kb, case) for case in cases]
    answerable = [r for r in results if not r.should_refuse]
    refuse = [r for r in results if r.should_refuse]
    facts_total = sum(r.facts_total for r in answerable)
    return AnswerReport(
        citation_accuracy=sum(1 for r in answerable if r.cited_expected) / max(1, len(answerable)),
        key_fact_coverage=sum(r.facts_found for r in answerable) / max(1, facts_total),
        refusal_accuracy=sum(1 for r in results if r.handled_correctly) / max(1, len(results)),
        refusal_recall=sum(1 for r in refuse if r.handled_correctly) / max(1, len(refuse)),
        false_refusal_rate=sum(1 for r in answerable if not r.handled_correctly) / max(1, len(answerable)),
        retrieval_p50_ms=percentile([r.retrieval_ms for r in results], 0.5),
        retrieval_p95_ms=percentile([r.retrieval_ms for r in results], 0.95),
        answer_p50_ms=percentile([r.answer_ms for r in results], 0.5),
        answer_p95_ms=percentile([r.answer_ms for r in results], 0.95),
        providers=dict(Counter(f"{r.provider}:{r.model}" for r in results)),
        cases=results,
    )


# Threshold sweep


@dataclass(frozen=True)
class SweepRow:
    threshold: float
    accuracy: float
    refusal_recall: float
    answer_rate: float


def sweep_thresholds(
    kb: SampleKnowledgeBase, cases: Sequence[EvalCase], *, steps: int = 25
) -> list[SweepRow]:
    """Relevance gate accuracy at a range of thresholds, from one retrieval per case.

    accuracy counts a case as right when the gate alone makes the right call (decline
    should refuse questions, pass answerable ones), which is what the threshold
    controls; the model's own "not found" replies come on top of it.
    """
    scored = [
        (case.should_refuse, search(kb.organization_id, case.question).top_similarity) for case in cases
    ]
    highest = max((score or 0.0) for _, score in scored)
    rows: list[SweepRow] = []
    for step in range(steps + 1):
        threshold = round(highest * step / steps, 4)
        passes = [(refuse, score is not None and score >= threshold) for refuse, score in scored]
        refuse_cases = [p for refuse, p in passes if refuse]
        answer_cases = [p for refuse, p in passes if not refuse]
        rows.append(
            SweepRow(
                threshold=threshold,
                accuracy=sum(1 for refuse, p in passes if p != refuse) / max(1, len(passes)),
                refusal_recall=sum(1 for p in refuse_cases if not p) / max(1, len(refuse_cases)),
                answer_rate=sum(1 for p in answer_cases if p) / max(1, len(answer_cases)),
            )
        )
    return rows


# Reporting


@dataclass
class EvalRun:
    embedder: str
    threshold: float
    documents: int
    cases: int
    retrieval: list[RetrievalReport] = field(default_factory=list)
    answers: AnswerReport | None = None
    sweep: list[SweepRow] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def run(
    *,
    modes: Sequence[Mode] = MODES,
    k: int = 5,
    answers: bool = True,
    sweep: bool = False,
    cases: Sequence[EvalCase] | None = None,
) -> EvalRun:
    from assistant.retrieval import relevance_threshold, resolve_query_embedder

    cases = list(cases or load_cases())
    with sample_knowledge_base() as kb:
        embedder = resolve_query_embedder(kb.organization_id)
        report = EvalRun(
            embedder=embedder.name,
            threshold=relevance_threshold(embedder),
            documents=len(kb.documents),
            cases=len(cases),
        )
        report.retrieval = [evaluate_retrieval(kb, cases, mode=mode, k=k) for mode in modes]
        if answers:
            report.answers = evaluate_answers(kb, cases)
        if sweep:
            report.sweep = sweep_thresholds(kb, cases)
    return report


def _pct(value: float) -> str:
    return f"{value * 100:5.1f}%"


def format_report(report: EvalRun, *, verbose: bool = False) -> str:
    lines = [
        f"Sample knowledge base: {report.documents} documents, {report.cases} cases",
        f"Embedder: {report.embedder}   relevance threshold: {report.threshold:.3f}",
        "",
        "Retrieval (answerable cases)",
    ]
    if report.retrieval:
        cutoffs = sorted(report.retrieval[0].hit_rate_at)
        header = "  mode      " + "".join(f"  hit@{cut:<3}" for cut in cutoffs) + "    MRR    p50 ms   p95 ms"
        lines.append(header)
        for row in report.retrieval:
            hits = "".join(f"  {_pct(row.hit_rate_at[cut])}" for cut in cutoffs)
            lines.append(
                f"  {row.mode:<9}{hits}   {row.mrr:.3f}  {row.latency_p50_ms:7.1f}  {row.latency_p95_ms:7.1f}"
            )
    answers = report.answers
    if answers is not None:
        lines += [
            "",
            "Answers ("
            + ", ".join(f"{name} x{count}" for name, count in sorted(answers.providers.items()))
            + ")",
            f"  citation accuracy   {_pct(answers.citation_accuracy)}",
            f"  key fact coverage   {_pct(answers.key_fact_coverage)}",
            f"  refusal accuracy    {_pct(answers.refusal_accuracy)}"
            f"   (refused when out of scope {_pct(answers.refusal_recall)},"
            f" wrongly refused {_pct(answers.false_refusal_rate)})",
            f"  retrieval latency   p50 {answers.retrieval_p50_ms:.1f} ms"
            f"   p95 {answers.retrieval_p95_ms:.1f} ms",
            f"  answer latency      p50 {answers.answer_p50_ms:.1f} ms   p95 {answers.answer_p95_ms:.1f} ms",
        ]
        if verbose:
            lines += ["", "Cases"]
            for case in answers.cases:
                mark = "ok  " if case.handled_correctly and case.cited_expected is not False else "MISS"
                similarity = f"{case.top_similarity:.3f}" if case.top_similarity is not None else "  -  "
                facts = f"{case.facts_found}/{case.facts_total}" if case.facts_total else "   "
                lines.append(
                    f"  {mark} {case.case_id:<22} sim {similarity}  facts {facts}  {case.answer_type}"
                )
                lines.append(f"       {case.content[:160]}")
    if report.sweep:
        lines += ["", "Relevance threshold sweep (gate only)", "  threshold  accuracy  refused oos  answered"]
        best = max(point.accuracy for point in report.sweep)
        for point in report.sweep:
            flag = "  <- best" if point.accuracy == best else ""
            lines.append(
                f"  {point.threshold:9.4f}   {_pct(point.accuracy)}     {_pct(point.refusal_recall)}"
                f"     {_pct(point.answer_rate)}{flag}"
            )
    return "\n".join(lines)
