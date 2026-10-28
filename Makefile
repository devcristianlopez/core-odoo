SHELL := /bin/bash

# Per-directory execution
# -----------------------
# Every subproject owns its own tool configuration: orchestrator/, gateway/ and
# cli/ declare pytest and ruff settings in their own pyproject.toml
# (testpaths = ["tests"], line-length, lint selection), and mission-control has
# its own eslint / vitest / tsconfig setup. The suites are therefore always run
# from inside their own directory so pytest and ruff resolve that
# pyproject.toml as rootdir/config. Running them from the repository root would
# collect projects/, templates/ and data/iterations instead and fail with
# ImportPathMismatchError (or ModuleNotFoundError: odoo).
#
# Suites fail fast: the first failing suite is reported and the target stops.
# test and lint need mission-control/node_modules, so both check for it before
# the JS step and print the fix instead of an opaque "vitest: not found".

PY_PROJECTS := orchestrator gateway cli
JS_PROJECT  := mission-control
JS_DEPS     := [ -d $(JS_PROJECT)/node_modules ]

.PHONY: init up down restart status logs test lint skills fmt e2e clean

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
	@set -eu; \
	for dir in $(PY_PROJECTS); do \
		printf '\n>>> pytest (%s)\n' "$$dir"; \
		(cd $$dir && uv run pytest -q) \
			|| { printf '\n*** FAILED: pytest in %s\n' "$$dir"; exit 1; }; \
	done; \
	$(JS_DEPS) \
		|| { printf "\n*** mission-control/node_modules missing: run 'npm --prefix mission-control ci'\n"; exit 1; }; \
	printf '\n>>> vitest (%s)\n' "$(JS_PROJECT)"; \
	(cd $(JS_PROJECT) && npm run test) \
		|| { printf '\n*** FAILED: vitest in %s\n' "$(JS_PROJECT)"; exit 1; }

lint:
	@set -eu; \
	for dir in $(PY_PROJECTS); do \
		printf '\n>>> ruff check (%s)\n' "$$dir"; \
		(cd $$dir && uv run ruff check .) \
			|| { printf '\n*** FAILED: ruff check in %s\n' "$$dir"; exit 1; }; \
	done; \
	$(JS_DEPS) \
		|| { printf "\n*** mission-control/node_modules missing: run 'npm --prefix mission-control ci'\n"; exit 1; }; \
	printf '\n>>> eslint (%s)\n' "$(JS_PROJECT)"; \
	(cd $(JS_PROJECT) && npm run lint) \
		|| { printf '\n*** FAILED: eslint in %s\n' "$(JS_PROJECT)"; exit 1; }; \
	printf '\n>>> tsc --noEmit (%s)\n' "$(JS_PROJECT)"; \
	(cd $(JS_PROJECT) && npx tsc --noEmit) \
		|| { printf '\n*** FAILED: tsc --noEmit in %s\n' "$(JS_PROJECT)"; exit 1; }; \
	printf '\n>>> tsc --noEmit -p tsconfig.node.json (%s)\n' "$(JS_PROJECT)"; \
	(cd $(JS_PROJECT) && npx tsc --noEmit -p tsconfig.node.json) \
		|| { printf '\n*** FAILED: tsc --noEmit -p tsconfig.node.json in %s\n' "$(JS_PROJECT)"; exit 1; }
	@printf '\n>>> skills (frontmatter + links + symlinks)\n'; python3 scripts/check_skills.py

skills:
	@python3 scripts/check_skills.py

fmt:
	@set -eu; \
	for dir in $(PY_PROJECTS); do \
		printf '\n>>> ruff format (%s)\n' "$$dir"; \
		(cd $$dir && uv run ruff format .) \
			|| { printf '\n*** FAILED: ruff format in %s\n' "$$dir"; exit 1; }; \
	done

e2e:
	@./scripts/e2e.sh

clean:
	docker compose -f docker-compose.yml -f docker-compose.observability.yml down -v --remove-orphans
