# 0002. Factories and application lifecycle

- **Status:** Accepted
- **Date:** 2026-10-25

## Context

The app holds resources such as the LLM client's connection pool, and later database
and vector-store clients. They must be created from configuration, handed to the
routes that need them, and closed predictably. Each test needs an isolated app with
its own settings.

## Decision

**Factories create objects.** There are three, one per level:

| Factory | Decides | Location |
| --- | --- | --- |
| `create_app(settings=None)` | how the whole app is wired | `app/main.py` |
| `build_llm_provider(settings)` | **which** provider to create | `app/llm/factory.py` |
| `OpenAIProvider.from_settings(settings)` | **how** to build it from config | `app/llm/providers/openai.py` |

```python
def build_llm_provider(settings: Settings) -> LLMProvider:   # returns the interface
    if settings.llm_provider == "mock":
        return MockProvider()
    if missing:                                               # key or model not set
        return UnconfiguredProvider(reason)
    return OpenAIProvider.from_settings(settings)
```

`OpenAIProvider.__init__` takes a ready-made client; `from_settings` builds that client
from configuration. Factories only construct objects; they make no requests.

**The lifespan owns resources.** It calls the factories at startup, stores the result
on `app.state`, and closes it at shutdown:

```python
@asynccontextmanager
async def lifespan(app):
    resolved = settings or get_settings()          # read at startup, not on import
    app.state.llm_provider = build_llm_provider(resolved)
    try:
        yield                                      # app serves requests
    finally:
        await app.state.llm_provider.aclose()      # always closed
```

**Dependency injection delivers resources to routes.** Routes never read `app.state`
directly:

```python
def get_llm_provider(request: Request) -> LLMProvider:
    return request.app.state.llm_provider

async def chat(request: ChatRequest, llm: Annotated[LLMProvider, Depends(get_llm_provider)]): ...
```

**Rule:** importing a module only defines things. Reading files, opening connections
and other side effects belong in the lifespan.

## Why

- The choice of implementation lives in one place; callers only see the interface.
- Splitting `__init__` (takes dependencies) from `from_settings` (builds them) lets
  tests inject a fake client.
- Resources are created and closed in one place, so cleanup is guaranteed.
- Each app instance, including each test app, is isolated and explicitly configured.
- Routes stay testable via `app.dependency_overrides`.

## Alternatives considered

- **Module-level singletons (`@lru_cache`)** - global state that tests cannot isolate
  and overrides do not reach.
- **Factory classes (GoF Factory Method / Abstract Factory)** - unnecessary in Python; a
  function is enough and easy to replace. A lookup table can replace the `if` chain
  once there are many providers.
- **`@app.on_event` hooks** - deprecated in favour of the lifespan.

## Consequences

- Tests must run the lifespan: `with TestClient(app) as client:`.
- `app.state` is untyped, so access always goes through typed dependency functions.
- New resources follow the same pattern: a factory builds it, the lifespan stores it
  on `app.state` and closes it, a `get_x()` dependency exposes it.
