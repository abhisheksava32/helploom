# Evaluation harness

`evals/` measures retrieval and answer quality on a small, realistic knowledge base.
It is a plain package (not a Django app); the `run_evals` management command in the
assistant app drives it.

```bash
uv run python manage.py run_evals                     # every retrieval mode plus answers
uv run python manage.py run_evals --sweep             # also sweep the relevance threshold
uv run python manage.py run_evals --verbose           # print every case and its answer
uv run python manage.py run_evals --provider claude --embedder ollama
uv run python manage.py run_evals --json report.json  # full machine readable report
```

The run ingests `kb/` into a throwaway organisation through the same upload and
ingestion code customers use, inside one transaction that is rolled back, with
uploaded files written to a temporary directory. Nothing is left behind.

## Contents

| Path | What it is |
| --- | --- |
| `kb/` | Six support documents for Kettlewick Coffee Co., a fictional roaster, in every supported format: Markdown, HTML, plain text, Word and PDF |
| `cases.json` | 40 answerable questions (expected document and key facts) and 8 out of scope questions that must get the "not found" answer |
| `runner.py` | Scoring, the threshold sweep and the text report |
| `samples.py` | Builds the Word and PDF samples from reviewable text (`uv run python -m evals.samples`); the tests reuse its PDF and DOCX builders |
| `tests/` | Runs the harness as a regression test with quality floors |

## Metrics

- **hit rate at k**: share of answerable questions whose expected document is among
  the top k passages.
- **MRR**: mean reciprocal rank of the first passage from the expected document.
- **citation accuracy**: share of answerable questions whose answer cites the
  expected document.
- **key fact coverage**: share of expected facts (for example "30 days") that appear
  in the answers.
- **refusal accuracy**: share of all questions handled correctly; out of scope
  questions must be refused and answerable ones must not.
- **latency**: retrieval and full answer p50 and p95.

## Current results

Hashing embedder and extractive provider, fully offline (the configuration the test
suite runs):

| Mode | hit@1 | hit@3 | hit@5 | MRR |
| --- | --- | --- | --- | --- |
| vector | 95.0% | 100.0% | 100.0% | 0.975 |
| keyword | 95.0% | 100.0% | 100.0% | 0.975 |
| hybrid | 97.5% | 100.0% | 100.0% | 0.988 |

| Answers | Value |
| --- | --- |
| citation accuracy | 97.5% |
| key fact coverage | 71.4% |
| refusal accuracy | 100.0% |
| retrieval latency | about 7 ms p50 |

Hybrid search beats either side alone at the top rank, which is the case for running
both. Key fact coverage is the extractive provider's ceiling: it can only quote
sentences, so a question like "How often can a subscription deliver?" picks the
sentence with the most overlapping words rather than the one that says "every 1, 2,
3 or 4 weeks". A language model provider closes that gap; rerun with
`--provider ollama` or `--provider claude` to compare.

## Calibrating the relevance threshold

`--sweep` reports, for a range of thresholds, how often the relevance gate alone
makes the right call. For the hashing embedder the highest out of scope similarity
is about 0.14 and the lowest answerable one about 0.16, so its default threshold is
0.15. Similarity scales differ between embedders: run the sweep with
`--embedder ollama` before trusting the Ollama default, and set
`RELEVANCE_THRESHOLD` if your own documents need a different cut.
