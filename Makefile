.PHONY: setup db-up db-down db-reset migrate migration migrate-down migrate-current migrate-history migrate-check sample-data api lint format test test-unit test-integration test-e2e

setup:
	uv sync --all-extras

db-up:
	docker compose up -d --wait db

db-down:
	docker compose down

# DESTROYS local dev data: drops the Postgres volume, restarts it and re-applies all migrations.
db-reset:
	docker compose down -v
	docker compose up -d --wait db
	uv run alembic upgrade head

migrate:
	uv run alembic upgrade head

migrate-down:
	uv run alembic downgrade -1

migrate-current:
	uv run alembic current

migrate-history:
	uv run alembic history --verbose

# Fails if the models and the migrations have drifted apart (a model change without a migration).
migrate-check:
	uv run alembic check

# usage: make migration m="add sha256 column"
migration:
	@test -n "$(m)" || { echo 'usage: make migration m="describe the change"'; exit 1; }
	uv run alembic revision --autogenerate -m "$(m)"

sample-data:
	uv run python scripts/generate_sample_data.py

api:
	uv run uvicorn --factory app.main:create_app --reload --port 8001

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy app

format:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest

test-unit:
	uv run pytest tests/unit

test-integration:
	uv run pytest tests/integration

test-e2e:
	uv run pytest tests/e2e
