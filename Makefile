.PHONY: up down build migrate seed lint typecheck arch test-unit test-api test-fe test-jobs check coverage openapi reset e2e e2e-install smoke prod-up prod-down

up:
	@test -f .env || cp .env.example .env
	docker compose up -d --build

down:
	docker compose down

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

test-unit:
	cd backend && uv run pytest tests/unit

test-api:
	docker compose run --rm api pytest tests/api tests/integration

test-jobs:
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
	docker compose run --rm api sh -c "pytest tests --cov=app --cov-report=term-missing && python scripts/check_coverage.py"

openapi:
	cd backend && uv run python scripts/export_openapi.py
	cd frontend && npx openapi-typescript ../backend/openapi.json -o src/api/schema.d.ts

reset:
	docker compose down -v
	docker compose up -d --build
