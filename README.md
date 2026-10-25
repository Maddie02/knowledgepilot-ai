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
and a chat endpoint that can call an OpenAI model (or a deterministic mock).
Document upload, answers with sources, and agent-based workflow automation are
planned features and are not implemented yet. The setup below runs the current
backend locally.

## How the app works

`app/main.py` builds the FastAPI application in `create_app()` and registers the
health and chat routers. `GET /health` returns `{"status": "healthy"}` and does
not call any external service. `POST /api/v1/chat` validates the request and
passes the message to the configured LLM provider (see [Chat API](#chat-api)).

The application owns its resources through FastAPI's *lifespan*: at startup it
reads the settings, creates the LLM provider and stores it on `app.state`; at
shutdown it closes it (including the provider's HTTP connection pool). Routes
receive the provider through the `get_llm_provider` dependency in
`app/api/dependencies.py`. Future clients (databases, vector stores) follow the
same pattern.

The tests use FastAPI's `TestClient` to call the application without starting a
separate server. Each test builds its own app with explicit settings through
the fixtures in `tests/conftest.py`, so a local `.env` is never read during
tests (a guard fails any test that tries). They always use the mock model or a
mocked HTTP transport, so they never make paid requests.

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

## Chat API

`POST /api/v1/chat` accepts a message and returns a reply from the configured
LLM provider. By default it uses a deterministic mock model (`MockProvider`),
so no API key or network access is needed and the same input always produces
the same output. See [Configuration](#configuration) to use a real model.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is our vacation policy?"}'
```

Mock response:

```json
{"reply": "Mock response to: What is our vacation policy?", "model": "mock-llm", "usage": null}
```

With a real provider, `model` is the configured model ID and `usage` contains
the token counts the provider reported (`null` if it reported none):

```json
{
  "reply": "...",
  "model": "<OPENAI_MODEL>",
  "usage": {"input_tokens": 42, "output_tokens": 120, "total_tokens": 162}
}
```

Request rules (violations return `422 Unprocessable Content`):

- `message` is required and must be a string.
- Leading and trailing whitespace is removed; the result must be 1–4000
  characters, so empty or whitespace-only messages are rejected.
- Unknown fields are rejected.
- The body must be valid JSON.

Provider failures return a generic message. Provider details, credentials and
SDK error messages are never sent to the client; the server logs only the
error type, HTTP status and provider request ID.

| Situation | Status | `detail` |
| --- | --- | --- |
| Provider not configured, or key/model rejected | `503` | `LLM provider is not configured` |
| Provider rate limit or quota (may include `Retry-After`) | `503` | `LLM provider is busy, try again later` |
| Provider did not respond within the timeout | `504` | `LLM provider timed out` |
| Any other provider or connection error | `502` | `LLM provider error` |

The route in `app/api/routers/chat.py` only validates input and delegates to an
`LLMProvider` supplied via FastAPI dependency injection (`get_llm_provider` in
`app/api/dependencies.py`). All OpenAI SDK code lives in
`app/llm/providers/openai.py`.

## Configuration

Settings are read from environment variables and from a `.env` file in the
project root (environment variables take precedence). Copy the template and
fill in your values:

```bash
cp .env.example .env
```

`.env` is ignored by Git. Never commit real credentials; `.env.example` must only
contain placeholders.

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER` | `mock` | `mock` or `openai` |
| `OPENAI_API_KEY` | – | Provider API key (required for `openai`) |
| `OPENAI_MODEL` | – | Model ID to request (required for `openai`) |
| `OPENAI_BASE_URL` | OpenAI | Optional OpenAI-compatible endpoint |
| `LLM_TIMEOUT_SECONDS` | `30` | Timeout for each provider request attempt |
| `LLM_MAX_RETRIES` | `2` | Automatic retries on connection errors, 429 and 5xx |
| `LLM_SYSTEM_PROMPT` | built-in | System instructions sent with every request |
| `LLM_TEMPERATURE` | provider default | Sampling temperature (0–2) |
| `LLM_MAX_OUTPUT_TOKENS` | provider default | Upper limit on generated tokens |
| `LOG_LEVEL` | `INFO` | Minimum level for application logs (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

To use OpenAI, set `LLM_PROVIDER=openai`, `OPENAI_API_KEY` and `OPENAI_MODEL`,
then restart the server. If the provider is `openai` but the key or model is
missing, the app still starts (so `/health` works) and chat requests return
`503`.

The worst-case response time is roughly
`LLM_TIMEOUT_SECONDS × (LLM_MAX_RETRIES + 1)` plus retry back-off.

### Experiments

Each successful request logs the model, latency and token counts in the server
terminal, e.g.
`INFO      app.llm.providers.openai - LLM request completed model=... latency_ms=840 input_tokens=42 output_tokens=120`.
At startup the server also logs which provider and model it uses, or a warning
if required settings are missing. Logs never include the API key or provider
error messages.
To compare behaviour, change `LLM_SYSTEM_PROMPT`, `LLM_TEMPERATURE` or
`LLM_MAX_OUTPUT_TOKENS` in `.env` and restart. Asking about a fictional internal
procedure (e.g. "What is the approval process for form KP-17?") shows that the
model has no access to company knowledge and may invent an answer.

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
| `make test` | Run the automated tests (never calls a real provider) |
| `make test-live` | Run the live smoke test against the provider in `.env` (costs money) |
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
  main.py                    # Composition root: create_app(), lifespan (owns resources)
  core/                      # Cross-cutting infrastructure
    config.py                #   Settings loaded from env / .env (pydantic-settings)
    logging_setup.py         #   Sends app.* logs to the terminal at LOG_LEVEL
    exception_handlers.py    #   Maps LLM errors to safe HTTP responses (logs metadata only)
  api/                       # Web layer
    dependencies.py          #   FastAPI dependencies for app-owned resources (get_llm_provider)
    routers/
      health.py              #   GET /health
      chat.py                #   POST /api/v1/chat
  schemas/
    chat.py                  # Request/response models (DTOs)
  llm/                       # LLM integration
    __init__.py              #   Public API - import from `app.llm`, not submodules
    types.py                 #   LLMProvider interface (Protocol), LLMResult, LLMUsage
    errors.py                #   Provider-neutral LLMError hierarchy
    factory.py               #   build_llm_provider(settings): picks the implementation
    providers/
      mock.py                #   MockProvider (deterministic, no network)
      unconfigured.py        #   UnconfiguredProvider (missing config -> 503)
      openai.py              #   OpenAIProvider (only module that imports the openai SDK)
  services/                  # Business logic (empty for now; e.g. RAG orchestration later)
tests/                       # Mirrors app/
  conftest.py                # App/client fixtures with explicit settings; blocks reading .env
  test_app_lifecycle.py      # Lifespan: provider creation, isolation, shutdown, overrides
  api/
    test_chat.py             #   Chat API, validation, error mapping and logs
    test_health.py           #   Health check
  core/
    test_config.py           #   Settings loading, masking and validation
    test_logging.py          #   Logging configuration
  llm/
    test_factory.py          #   Provider selection
    test_openai_provider.py  #   OpenAI provider over a mocked HTTP transport
    test_live_openai.py      #   Optional live smoke test (marker: live)
.env.example                 # Configuration template (placeholders only)
Makefile                     # Development command shortcuts
pyproject.toml               # Project metadata, dependencies and pytest settings
uv.lock                      # Locked dependency versions
```

Dependencies point one way: `api` → `llm` / `schemas` → `core`. Inside `llm`,
providers depend only on `types` and `errors`, and `factory` depends on the
providers, so there are no circular imports.
