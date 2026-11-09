.PHONY: setup hooks local docker services down logs clean migrate migration migrate-down migrate-current migrate-history migrate-check migrate-heads migrate-roundtrip sample-data lint format test test-unit test-integration test-e2e

setup:
	uv sync --all-extras

# One-time: install the git pre-commit hook (ruff + file hygiene, see .pre-commit-config.yaml).
hooks:
	uv run pre-commit install

# Both start from an empty database and image store every time (see `clean`), and serve the API on the same port.
export API_PORT ?= 8000

# Run on the host: Postgres + Redis in Docker, migrations, then the API with reload on http://localhost:$(API_PORT).
local: setup clean services migrate
	uv run uvicorn --factory app.main:create_app --reload --port $(API_PORT)

# The whole stack in Docker: Postgres, Redis, a one-shot migration, then the API on http://localhost:$(API_PORT).
docker: clean
	docker compose up -d --build --wait api

# Backing services only (for `make test`): Postgres, plus Redis for the rate limiter.
services:
	docker compose up -d --wait db redis

down:
	docker compose down

logs:
	docker compose logs -f api

# DESTROYS dev data: stops the stack, drops its volumes (Postgres, Docker image store) and the host image store.
clean:
	docker compose down -v --remove-orphans
	rm -rf local_storage

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

# Fails unless the revision history has exactly one head (two branches that each added a migration).
migrate-heads:
	@heads=$$(uv run alembic heads | grep -c .); \
	if [ "$$heads" -ne 1 ]; then echo "expected 1 alembic head, found $$heads:"; uv run alembic heads; exit 1; fi

# Every downgrade() must work and the schema must rebuild from nothing. DESTROYS data in the target database.
migrate-roundtrip:
	uv run alembic upgrade head
	uv run alembic downgrade base
	uv run alembic upgrade head

# usage: make migration m="add sha256 column"
migration:
	@test -n "$(m)" || { echo 'usage: make migration m="describe the change"'; exit 1; }
	uv run alembic revision --autogenerate -m "$(m)"

sample-data:
	uv run python scripts/generate_sample_data.py

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

format:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest $(PYTEST_ARGS)

test-unit:
	uv run pytest tests/unit

test-integration:
	uv run pytest tests/integration

test-e2e:
	uv run pytest tests/e2e
