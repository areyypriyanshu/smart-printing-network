.PHONY: up down build migrate seed lint typecheck arch test-unit test-api test-fe check openapi reset

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

test-fe:
	cd frontend && npm run test

check: lint typecheck arch test-unit test-fe

openapi:
	cd backend && uv run python scripts/export_openapi.py
	cd frontend && npx openapi-typescript ../backend/openapi.json -o src/api/schema.d.ts

reset:
	docker compose down -v
	docker compose up -d --build
