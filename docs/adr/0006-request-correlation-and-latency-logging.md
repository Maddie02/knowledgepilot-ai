# 0006. Request correlation and latency logging

- **Status:** Proposed
- **Date:** 2026-10-29

## Context

Many requests run at the same time, so their log lines interleave. We need to tell
which lines belong to one request, and to see how long requests take, especially
streams, where the total time hides how long the user waited for the first text.
Logs must not expose message text, query strings or credentials.

## Decision

- **Every HTTP request has a request ID.** A pure ASGI middleware
  (`app/api/middleware.py`) reuses an incoming `X-Request-ID` header if it matches
  `[A-Za-z0-9._-]{1,64}`, and otherwise generates a UUID (32 hex characters). The ID
  is returned in the `X-Request-ID` response header.
- **The ID is stored in a `ContextVar`** (`app/core/request_context.py`) for the
  duration of the request and reset afterwards.
- **A logging filter adds it to every `app.*` log line** as `[request_id]`, or `[-]`
  outside a request:
  ```text
  INFO  app.api.routers.chat [9f2c...] - LLM stream ended outcome=completed deltas=29 ...
  INFO  app.api.middleware   [9f2c...] - HTTP request method=POST path=/api/v1/chat/stream status=200 duration_ms=950
  ```
- **One line per HTTP request** from the middleware: method, path (without the query
  string), status and `duration_ms`. For streams, the duration covers the whole stream.
- **Streams also log `ttft_ms`** (time to first token, `None` if no text was sent)
  and `total_ms` in their summary line (see [ADR-0005](0005-streaming-chat-protocol.md)).
- Only fixed fields are logged: never message or reply text, headers, query strings
  or exception messages.

## Why

- A `ContextVar` follows the request through every `await` and into tasks started
  while handling it, including FastAPI's SSE producer task, without passing the ID
  through every function.
- Reusing a caller's ID lets a client or gateway correlate its own logs with ours.
  Validating it stops log injection (newlines) and log flooding (very long values).
- Time to first token is what streaming improves; total time alone would hide it.

## Alternatives considered

- **`BaseHTTPMiddleware`** - simpler to write, but it wraps the response body and
  runs the endpoint in a separate task, which complicates streaming responses.
- **Passing the ID as a function argument** - every layer, including providers,
  would need an extra parameter only for logging.
- **Always generating the ID** - simpler, but loses correlation with upstream callers.
- **Structured (JSON) logs or OpenTelemetry tracing** - better for production log
  tooling, but more setup than this project needs today. The `ContextVar` makes a
  later switch easy.

## Consequences

- Log lines from `app.*` include `[request_id]`. Uvicorn's own access log does not;
  the middleware line replaces it for correlation.
- Code that starts background work outside a request must not expect a request ID.
- An `X-Request-ID` sent by a client is trusted only as a label, never for
  authorisation.
