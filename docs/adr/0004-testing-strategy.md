# 0004. Testing strategy

- **Status:** Accepted
- **Date:** 2026-10-25

## Context

The app calls a paid API and handles secrets. Tests must be fast, free and
deterministic, independent of the developer's machine, and must prove the safety
properties we rely on.

## Decision

- **No paid calls by default.** Test apps use the mock provider. The OpenAI provider
  is tested through the real SDK client with a fake HTTP transport:
  ```python
  client = AsyncOpenAI(
      api_key="sk-test",
      max_retries=0,
      http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
  )
  provider = OpenAIProvider(client=client, model="test-model", system_prompt="...")
  ```
- **One optional live test**, marked `live`: excluded by default, run with
  `make test-live`, and skipped without credentials.
- **Isolation:** fixtures in `tests/conftest.py` build each app with explicit settings
  (`make_app`, `app`, `client`); a guard fails any test that reads `.env`;
  dependencies are swapped with `app.dependency_overrides`.
- **Coverage focus:** API contract, error mapping including log lines, provider
  behaviour for each failure type, lifecycle (creation, isolation, shutdown), and
  architecture rules.
- **Safety tests must be seen failing once:** reintroduce the bug, confirm the test
  fails, then restore. A test that cannot fail proves nothing.
- `tests/` mirrors `app/`; async tests use `pytest.mark.anyio`.

## Why

- The real SDK with a fake transport tests real request building, parsing and error
  types without network access or cost.
- Explicit settings and the guard keep results identical on every machine and in CI.
- Checking that a test can fail prevents false confidence in security checks.

## Alternatives considered

- **Mocking the SDK client object** - skips the SDK's real parsing and error types.
- **Recorded responses (VCR-style)** - needs a paid recording and stored data that may be sensitive.
- **Live tests in CI** - costs money per PR, needs a secret, and is flaky.

## Consequences

- `make test` and CI are offline, free and fast.
- Changes in real provider behaviour are only caught by `make test-live`; run it after
  upgrading the SDK or changing models.
- Tests that need the app use the fixtures, not `app.main.app`.
