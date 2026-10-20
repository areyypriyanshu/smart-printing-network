.PHONY: up down build migrate seed lint typecheck arch test-unit test-api test-fe test-jobs check coverage openapi reset e2e e2e-install smoke prod-up prod-down db-shell db-ui graph graph-check graph-query

up:
	@test -f .env || cp .env.example .env
	@./infra/scripts/generate-dev-secrets.sh
	docker compose --profile tools up -d --build

down:
	docker compose --profile tools down

build:
	docker compose build

migrate:
	docker compose run --rm api alembic upgrade head

seed:
	docker compose run --rm api python -m app.cli seed

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint && npm run format:check

typecheck:
	cd backend && uv run mypy app
	cd frontend && npm run typecheck

arch:
	cd backend && uv run lint-imports

# The unit tests need the two secrets the application refuses to start
# without. They are set here so the suite does not depend on a .env file,
# and so a value the developer has changed locally cannot change what the
# tests are about.
test-unit:
	cd backend && \
		JWT_SECRET=test-only-jwt-secret \
		FAKE_WEBHOOK_SECRET=test-only-fake-webhook-secret \
		uv run pytest tests/unit

test-api:
	@test -f .env || cp .env.example .env
	docker compose run --rm api pytest tests/api tests/integration

test-jobs:
	@test -f .env || cp .env.example .env
	docker compose run --rm api pytest tests/jobs

test-fe:
	cd frontend && npm run test

e2e:
	cd e2e && npm test

e2e-install:
	cd e2e && npm ci && npx playwright install chromium

# The whole product flow against a running stack: upload, price, pay,
# queue, accept, print, ready, pickup.
smoke:
	./infra/scripts/smoke-test.sh

# The production stack, which also runs locally. Caddy issues a
# certificate from its own local authority, so the browser warns once
# until that certificate is trusted.
prod-up:
	docker compose -f docker-compose.prod.yml up -d --build
	docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head

prod-down:
	docker compose -f docker-compose.prod.yml down

check: lint typecheck arch test-unit test-fe

# The coverage floors from AGENTS.md: 90% on domain and services, 80%
# overall. The whole suite runs in one container so the coverage data
# file survives to the check.
coverage:
	@test -f .env || cp .env.example .env
	docker compose run --rm api sh -c "pytest tests --cov=app --cov-report=term-missing && python scripts/check_coverage.py"

openapi:
	cd backend && FAKE_WEBHOOK_SECRET=test-only-fake-webhook-secret uv run python scripts/export_openapi.py
	cd frontend && npx openapi-typescript ../backend/openapi.json -o src/api/schema.d.ts

reset:
	docker compose --profile tools down -v
	docker compose --profile tools up -d --build

# An interactive psql session against the local database.
db-shell:
	docker compose exec db sh -c 'psql -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}"'

# The database browser, on http://localhost:5050. It is already part of
# `make up`; this target is for starting it on its own.
db-ui:
	docker compose --profile tools up -d pgadmin

# The knowledge graph of the repository: a node for every module, function,
# class, ADR and concept, and the edges between them. It is a map of the
# project, not a source of truth, and the session-start section of AGENTS.md
# explains how to use it. `make graph` re-extracts the code with the AST
# parser only, so it costs no tokens and is safe to run at the start of a
# session.
graph:
	graphify update . --force
	python3 infra/scripts/graphify-relabel.py

# Says whether the code has moved on since the graph was built.
graph-check:
	python3 infra/scripts/graphify-check.py

# Ask the graph a question:
#   make graph-query Q="how does an order become paid"
graph-query:
	graphify query "$(Q)" --budget 1500
