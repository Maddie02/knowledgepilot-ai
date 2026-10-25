# 0001. Provider-neutral LLM abstraction

- **Status:** Accepted
- **Date:** 2026-10-25

## Context

We need a mock for development and tests, a real model via the OpenAI SDK, and the
freedom to add other providers - without the rest of the app depending on any SDK.

## Decision

- An interface in `app/llm/types.py`, defined as a `Protocol`:
  ```python
  class LLMProvider(Protocol):
      async def generate(self, message: str) -> LLMResult: ...
      async def aclose(self) -> None: ...
  ```
- **Provider-neutral errors** in `app/llm/errors.py`: `LLMConfigurationError`,
  `LLMTimeoutError`, `LLMRateLimitError`, `LLMProviderError`. Providers translate SDK
  exceptions into these.
- **Implementations** in `app/llm/providers/`:
  - `MockProvider` - deterministic, no network, the default;
  - `UnconfiguredProvider` - used when required settings are missing; raises
    `LLMConfigurationError` on every call;
  - `OpenAIProvider` - the only module that imports the `openai` SDK; uses the
    **Responses API** with the system prompt as `instructions`, and configured
    timeout and retries.
- **One factory decides which provider to build:** `build_llm_provider(settings)` in
  `app/llm/factory.py` (see [ADR-0002](0002-factories-and-application-lifecycle.md)).

## Why

- Routes and tests never depend on an SDK, so providers can be swapped or added freely.
- A `Protocol` lets fakes and new providers satisfy the interface without inheritance.
- Translating errors in one place keeps SDK messages out of the API layer.

## Alternatives considered

- **Chat Completions API** - wider compatibility, but the Responses API is OpenAI's
  current API; another API can be added as a separate provider.
- **Abstract base class** - forces inheritance on every implementation.
- **Letting SDK exceptions propagate** - couples the API layer to one SDK.

## Consequences

- A new provider means one module in `providers/` plus one branch in the factory.
- Every provider must implement `generate` and `aclose` and map its own failures.
- Optional parameters (e.g. `temperature`) are only sent when set, because not every
  model supports them.
