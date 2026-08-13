COMPOSE := docker compose -f infra/docker/compose.yml

.PHONY: setup dev test lint typecheck security e2e load-test down

setup:
	pnpm install --frozen-lockfile
	cd services/api && uv sync --frozen
	cd services/worker && uv sync --frozen
	cd services/llm-gateway && uv sync --frozen

dev:
	$(COMPOSE) up --detach
	@echo "Core Serviq infrastructure is running. Start app and service processes in separate terminals."

test:
	pnpm test
	cd services/api && uv run pytest
	cd services/worker && uv run pytest
	cd services/llm-gateway && uv run pytest

lint:
	pnpm lint
	cd services/api && uv run ruff check .
	cd services/worker && uv run ruff check .
	cd services/llm-gateway && uv run ruff check .

typecheck:
	pnpm typecheck
	cd services/api && uv run mypy app tests
	cd services/worker && uv run mypy app tests
	cd services/llm-gateway && uv run mypy app tests

security:
	@echo "not yet implemented — see OPE-272"
	@false

e2e:
	@echo "not yet implemented — dedicated E2E coverage will land in a later ticket"
	@false

load-test:
	@echo "not yet implemented — dedicated load testing will land in a later ticket"
	@false

down:
	$(COMPOSE) down
