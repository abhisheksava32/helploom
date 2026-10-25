# Helploom

Helploom is an AI help desk for businesses. Upload your support documents (PDF, DOCX,
Markdown, TXT or HTML) and get a chat widget for your website that answers customer
questions from those documents, cites its sources, streams answers in real time, and
hands off to your team when the answer is not in your documentation.

> Status: under active development. The architecture, data model and API contract are
> in place; features are landing app by app.

## What it does

- **Document library** with drag and drop uploads, a live ingestion pipeline (queued,
  processing, ready or failed with a reason), tags, collections, text preview and
  re-indexing.
- **Grounded answers**: hybrid retrieval (pgvector cosine search plus PostgreSQL
  full-text search, fused with reciprocal rank fusion), a relevance threshold that
  produces an honest "I could not find that" instead of a guess, and structured
  citations.
- **Three answer providers** behind one interface: Ollama (default), the Claude API,
  and an offline extractive mode that needs no model at all.
- **Website widget**: one script tag, Shadow DOM, per organisation site key, origin
  allow list and rate limits.
- **Dashboard**: playground, conversation history with feedback and handoff tickets,
  support reports (answer rate, content gaps, top questions and documents, token
  cost), team roles and invitations, plans with usage limits, and Stripe or demo
  billing.

## Stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.13, uv, Django 5.2 LTS, Django REST Framework, Simple JWT, Channels + daphne |
| Data | PostgreSQL 18 with pgvector (HNSW) and full-text search (GIN) |
| AI | Ollama (llama3.2, nomic-embed-text), Anthropic Python SDK, local hashing embedder |
| Jobs and real time | In-process thread pool or Celery, in-memory or Redis channel layer |
| Frontend | Next.js (App Router), React, TypeScript strict, Tailwind CSS |

## Run it locally

Requirements: PostgreSQL with the pgvector extension available, [uv](https://docs.astral.sh/uv/)
and Node.js 20.9 or newer. Ollama is optional.

```bash
createdb helploom                 # if it does not exist yet
make install                      # creates backend/.env, installs dependencies
make migrate
make dev                          # API on http://localhost:8000, dashboard on http://localhost:3000
```

```bash
make test                         # backend tests (PostgreSQL) + frontend typecheck, lint, build
make lint
make help                         # every command
```

Configuration lives in `backend/.env` (documented in `backend/.env.example`) and
`frontend/.env.example`. `docker-compose.yml` describes the production stack
(PostgreSQL with pgvector, Redis, backend, Celery worker, frontend and Ollama); copy
`.env.example` to `.env` before `docker compose up`.

## Documentation

- [docs/DESIGN.md](docs/DESIGN.md): architecture, data model, request flows, the
  retrieval design and why, providers, multi-tenancy, security, scaling and
  trade-offs.
- [docs/API.md](docs/API.md): the REST and websocket contract.
