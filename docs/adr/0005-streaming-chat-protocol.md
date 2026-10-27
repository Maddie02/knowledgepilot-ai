# 0005. Streaming chat protocol

- **Status:** Accepted
- **Date:** 2026-10-27

## Context

Model replies can take many seconds. Clients should be able to show the reply while it
is being generated instead of waiting for the whole text. Once a streamed response has
started, its HTTP status can no longer change, so errors and cancellations need their
own rules.

## Decision

### Endpoint

- `POST /api/v1/chat/stream`, with the same `ChatRequest` body and validation as
  `POST /api/v1/chat`. The non-streaming endpoint is unchanged.
- The response uses **Server-Sent Events** (SSE), built with FastAPI's built-in support:
  the route is an async generator with `response_class=EventSourceResponse` and yields
  `ServerSentEvent` objects.
  ```python
  @router.post("/chat/stream", response_class=EventSourceResponse)
  async def chat_stream(request: ChatRequest, llm: ...) -> AsyncIterator[ServerSentEvent]:
      ...
      yield ServerSentEvent(event="delta", data=StreamDelta(text=...))
  ```
- Events have no `id:` or `retry:` fields. A stream cannot be resumed, and clients must
  not retry automatically, because every retry is a new paid model call.

### Events

Each event has a name and a JSON `data` payload. The payloads are Pydantic models in
`app/schemas/chat.py`.

| Event   | Payload                                    | When                                                                           |
| ------- | ------------------------------------------ | ------------------------------------------------------------------------------ |
| `delta` | `{"text": "..."}`                          | Zero or more times, one per model increment. `text` is never empty.            |
| `done`  | `{"model": "...", "usage": {...} \| null}` | Exactly once on success. Always the last event. `usage` matches `TokenUsage`.  |
| `error` | `{"detail": "..."}`                        | Exactly once on failure. Always the last event. Same shape as `ErrorResponse`. |

```text
event: delta
data: {"text": "Our vacation"}

event: delta
data: {"text": " policy is..."}

event: done
data: {"model": "gpt-4.1-mini", "usage": {"input_tokens": 42, "output_tokens": 7, "total_tokens": 49}}

```

A client builds the reply by joining the `delta` texts. A stream that closes **without**
a `done` or `error` event was cut off (network failure or server crash), and the client
must treat it as failed. FastAPI also sends keep-alive comment lines (`: ping`) during
quiet periods. Clients ignore them, and standard SSE parsers do this automatically.

### Errors

- **Request validation** fails before the stream starts, so it is a normal
  `422` response, as on `/chat`.
- **Every LLM failure** (configuration, rate limit, timeout, provider error) is sent as an
  `error` event, whether it happens before or after the first `delta`. The HTTP status is
  `200`, because it is sent before the provider is called. `detail` uses the same safe
  messages as `/chat` (`LLM provider timed out`, ...). The route maps errors with the same
  function the HTTP exception handler uses, so the messages cannot drift apart.
- A provider that finishes without producing any text sends an `error` event with
  `LLM provider error`, as `/chat` does with a 502.
- An unexpected (non-LLM) exception sends `{"detail": "Internal server error"}` and is
  logged with its traceback.
- After an `error` event, the server ends the stream.

### Cancellation

- When the client disconnects, FastAPI cancels the task that runs our generator, and the
  generator receives `asyncio.CancelledError` at its current `await`.
- The generator must close the upstream provider stream (in a `finally` or `async with`),
  log the outcome as `cancelled`, and **re-raise** the `CancelledError`. It is never
  swallowed and nothing more is sent.
- A disconnect is not an error and is logged at `INFO`.

### Provider contract

`LLMProvider` (see [ADR-0001](0001-provider-neutral-llm-abstraction.md)) gets a
streaming method next to `generate`:

```python
@dataclass(frozen=True)
class LLMTextDelta:
    text: str


@dataclass(frozen=True)
class LLMStreamEnd:
    model: str
    usage: LLMUsage | None = None


LLMStreamEvent = LLMTextDelta | LLMStreamEnd


class LLMProvider(Protocol):
    async def generate(self, message: str) -> LLMResult: ...
    def stream(self, message: str) -> AsyncIterator[LLMStreamEvent]: ...
    async def aclose(self) -> None: ...
```

- `stream` is declared with `def`, not `async def`. Calling an `async def` that contains
  `yield` returns an async iterator directly, with no `await`.
- Providers yield zero or more non-empty `LLMTextDelta`, then exactly one `LLMStreamEnd`.
- Failures are **raised** as the neutral `LLMError` subclasses. Providers never yield
  error values. The route turns them into `error` events.
- Providers release their upstream connection when the iterator is closed early.

### Logging

One summary line per stream, with fixed fields only: `outcome` (`completed`, `cancelled`
or `failed`), `ttft_ms` (time to first token), `total_ms`, number of deltas, token
counts, and the error type on failure. Message and reply text are never logged.
How logs are correlated with request IDs is a separate decision, in a follow-up ADR.

## Why

- SSE is plain HTTP and one-directional, which is all a chat reply needs. It works through
  proxies, is easy to inspect with `curl -N`, and has a standard wire format.
- FastAPI's built-in support handles the wire format and keep-alive pings, and documents
  the endpoint in OpenAPI, so we only write the event logic.
- Named events plus an explicit `done` let a client tell a complete reply apart from a cut-off one.
- Neutral stream events keep the API layer independent of the OpenAI event types.

## Alternatives considered

- **Read the first event before responding**, so early failures (bad configuration, rate
  limits) become real `503`/`504` statuses as on `/chat`. More consistent, but the route
  has to build the response by hand and loses the built-in keep-alive. Rejected for now
  for simplicity. A later ADR can adopt it.

## Consequences

- Clients must check the events, not the HTTP status. A `200` stream can still end in `error`.
- Browsers cannot use `EventSource`, which only supports `GET`. They must read the stream
  with `fetch()` and a `ReadableStream`, or use an SSE client library that supports `POST`.
- Every provider, including `MockProvider` and `UnconfiguredProvider`, must implement
  `stream`. The mock must be able to simulate delays and mid-stream failures for tests.
- Each delta is sent as soon as it arrives, with no server-side buffering. Because
  generators are pull-based, a slow client slows how fast we read from the provider.
- Proxies in front of the service must not buffer `text/event-stream` responses.
- Tests cover: a successful stream ending in `done`; a failure before the first `delta`;
  a failure mid-stream; and cancellation closing the upstream stream.
