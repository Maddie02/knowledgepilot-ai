.PHONY: start dev test lint

start:
	uv run uvicorn app.main:app

dev:
	uv run uvicorn app.main:app --reload

test:
	uv run python -m pytest

lint:
	uv run ruff check .
