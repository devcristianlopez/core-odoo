SHELL := /bin/bash

.PHONY: init up down restart status logs test lint fmt e2e clean

init:
	@./install.sh --dev

up:
	docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build

down:
	docker compose -f docker-compose.yml -f docker-compose.observability.yml down

restart: down up

status:
	@uv run --project cli core-odoo status

logs:
	docker compose logs -f --tail=200

test:
	@uv run --project orchestrator pytest -q
	@uv run --project gateway pytest -q

lint:
	@uv run --project orchestrator ruff check .
	@uv run --project gateway ruff check .
	@cd mission-control && npm run lint

fmt:
	@uv run --project orchestrator ruff format .
	@uv run --project gateway ruff format .

e2e:
	@./scripts/e2e.sh

clean:
	docker compose -f docker-compose.yml -f docker-compose.observability.yml down -v --remove-orphans
