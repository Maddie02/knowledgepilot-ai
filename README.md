# KnowledgePilot AI

**Enterprise AI Knowledge & Workflow Assistant**

KnowledgePilot AI is a planned AI platform where companies can upload internal
documents, ask questions, receive answers with source references, and automate
workflows through AI agents.

## Project vision

The goal is to help teams use their company's internal knowledge and automate
workflows in one place. The planned capabilities are:

- **Document upload:** Companies upload internal documents to make their
  knowledge available to the assistant.
- **Questions and answers:** Employees ask questions about the uploaded content
  in natural language.
- **Answers with sources:** Responses include references to the source documents
  so employees can verify the information.
- **Workflow automation:** AI agents help automate company workflows.

## Current status

The project currently contains a FastAPI backend with a health-check endpoint
and an automated test. Document upload, AI answers with sources, and agent-based
workflow automation are planned features and are not implemented yet. The setup
below runs the current backend locally.

## How the app works

`app/main.py` creates the FastAPI application and registers the health router
from `app/routers/health.py`. When a client sends `GET /health`, FastAPI calls the
health function and returns `{"status": "healthy"}` as JSON.

This endpoint is a basic check that the API can respond. It does not yet check
external services or run any AI functionality. The current code is the initial
backend foundation; AI features are not implemented yet.

`tests/test_health.py` uses FastAPI's `TestClient` to call the application without
starting a separate server. It checks both the HTTP status code (`200`) and the
JSON response.

## Requirements

- Python 3.13 or newer (the project pins Python 3.13 in `.python-version`)
- uv for Python environment and dependency management
- Make to run the shortcuts in `Makefile`

## Start locally

From the project root:

```bash
uv sync
make dev
```

`uv sync` creates the `.venv` environment and installs the project and development
dependencies using `uv.lock`. `make dev` starts the API with automatic reload
when you change the code. You do not need to activate `.venv` manually: the
Makefile uses `uv run` to select the project environment.

Once the server starts, open:

- API health check: <http://127.0.0.1:8000/health>
- Interactive API documentation: <http://127.0.0.1:8000/docs>

The health check returns:

```json
{"status": "healthy"}
```

The current health-check endpoint does not require an API key or a database.
Press `Ctrl+C` in the terminal to stop the server.

## Commands

The `Makefile` plays a similar role to the `scripts` section of `package.json`:
it gives longer commands short names. For example, `make dev` runs
`uv run uvicorn app.main:app --reload`.

In that command, `uv run` selects the project's Python environment, `uvicorn`
serves the web application, and `app.main:app` points to the `app` object inside
`app/main.py`. The `--reload` flag restarts the server when source files change.

Run these from the project root:

| Command | Purpose |
| --- | --- |
| `make dev` | Start the local server with automatic reload |
| `make start` | Start the server without automatic reload |
| `make test` | Run the automated tests |
| `make lint` | Check the code with Ruff |

If Make is unavailable, run the underlying commands directly:

```bash
uv run uvicorn app.main:app --reload
uv run uvicorn app.main:app
uv run python -m pytest
uv run ruff check .
```

Use `make test` or `uv run python -m pytest` to ensure tests use the project
environment and can import the `app` package.

## Project layout

```text
app/
  main.py           # FastAPI application and router registration
  routers/health.py # GET /health endpoint
  schemas/          # Package for data schemas
  services/         # Package for application services
tests/
  test_health.py    # Health-check test
Makefile            # Development command shortcuts
pyproject.toml      # Project metadata and dependencies
uv.lock             # Locked dependency versions
```
