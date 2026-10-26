# Development commands. Run from the repository root.
#   make install   install backend and frontend dependencies
#   make seed      create the demo workspace (demo@helploom.dev, password printed)
#   make dev       run the backend (:8000) and the frontend (:3000) together
#   make test      backend tests plus frontend typecheck, lint and build

SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND := backend
FRONTEND := frontend
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 3000

# Prefer the Node version pinned in frontend/.nvmrc when nvm has it installed.
NODE_VERSION := $(shell cat $(FRONTEND)/.nvmrc 2>/dev/null)
NVM_NODE_BIN := $(HOME)/.nvm/versions/node/v$(NODE_VERSION)/bin
ifneq ($(wildcard $(NVM_NODE_BIN)/node),)
export PATH := $(NVM_NODE_BIN):$(PATH)
endif

.PHONY: help install env migrate seed dev backend frontend worker test test-backend test-frontend \
	lint format typecheck evals reembed superuser check

help: ## Show this list
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-15s %s\n", $$1, $$2}'

install: env ## Install backend (uv) and frontend (npm) dependencies
	cd $(BACKEND) && uv sync
	cd $(FRONTEND) && npm install

env: ## Create backend/.env from the example with a random SECRET_KEY, if missing
	@if [ ! -f $(BACKEND)/.env ]; then \
		key=$$(cd $(BACKEND) && uv run python -c "import secrets; print(secrets.token_urlsafe(50))"); \
		sed -e "s|^SECRET_KEY=$$|SECRET_KEY=dev-$$key|" $(BACKEND)/.env.example > $(BACKEND)/.env; \
		echo "Created $(BACKEND)/.env"; \
	fi

migrate: ## Apply database migrations
	cd $(BACKEND) && uv run python manage.py migrate

seed: ## Create the demo workspace; prints the sign in details (seed ARGS=--reset to rebuild)
	cd $(BACKEND) && uv run python manage.py seed_demo $(ARGS)

dev: env ## Run backend and frontend together (Ctrl-C stops both)
	@trap 'kill 0' INT TERM EXIT; \
	(cd $(BACKEND) && uv run python manage.py runserver 127.0.0.1:$(BACKEND_PORT)) & \
	(cd $(FRONTEND) && npm run dev -- --port $(FRONTEND_PORT)) & \
	wait

backend: ## Run only the backend (ASGI dev server with websockets)
	cd $(BACKEND) && uv run python manage.py runserver 127.0.0.1:$(BACKEND_PORT)

frontend: ## Run only the frontend dev server
	cd $(FRONTEND) && npm run dev -- --port $(FRONTEND_PORT)

worker: ## Run a Celery worker (needs CELERY_BROKER_URL and Redis)
	cd $(BACKEND) && uv run celery --app helploom worker --loglevel INFO --queues helploom

test: test-backend test-frontend ## Run every test and build check

test-backend: ## Run the backend test suite against PostgreSQL
	cd $(BACKEND) && uv run pytest

test-frontend: typecheck ## Typecheck, lint and build the frontend
	cd $(FRONTEND) && npm run lint && npm run build

typecheck: ## TypeScript and mypy type checks
	cd $(FRONTEND) && npm run typecheck
	cd $(BACKEND) && uv run mypy .

lint: ## Lint backend (ruff) and frontend (eslint)
	cd $(BACKEND) && uv run ruff check . && uv run ruff format --check .
	cd $(FRONTEND) && npm run lint

format: ## Format and autofix backend code
	cd $(BACKEND) && uv run ruff format . && uv run ruff check --fix .

check: ## Django system checks and a missing migration check
	cd $(BACKEND) && uv run python manage.py check && uv run python manage.py makemigrations --check --dry-run

evals: ## Run the retrieval and answer evaluation harness
	cd $(BACKEND) && uv run python manage.py run_evals

reembed: ## Re-embed chunks created with a different embedder
	cd $(BACKEND) && uv run python manage.py reembed

superuser: ## Create a Django admin user
	cd $(BACKEND) && uv run python manage.py createsuperuser
