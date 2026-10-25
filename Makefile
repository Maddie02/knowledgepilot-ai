.PHONY: start dev test test-live coverage lint format typecheck check

start:
	uv run uvicorn app.main:app

dev:
	uv run uvicorn app.main:app --reload

test:
	uv run python -m pytest

# Calls the real provider configured in .env (costs money).
test-live:
	uv run python -m pytest -m live -v

# Tests with branch coverage; fails below the threshold in pyproject.toml.
coverage:
	uv run python -m pytest --cov --cov-report=term

lint:
	uv run ruff check .

# Rewrites files. CI only checks: `ruff format --check`.
format:
	uv run ruff format .

typecheck:
	uv run mypy

# Everything CI runs, in the same order.
check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	uv run python -m pytest --cov --cov-report=term
