.PHONY: start dev test test-live lint

start:
	uv run uvicorn app.main:app

dev:
	uv run uvicorn app.main:app --reload

test:
	uv run python -m pytest

# Calls the real provider configured in .env (costs money).
test-live:
	uv run python -m pytest -m live -v

lint:
	uv run ruff check .
