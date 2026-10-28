import asyncio
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from app.api.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from app.core.logging_setup import RequestIdFilter
from app.core.request_context import request_id_var


@pytest.fixture
def request_logs(caplog):
    """Capture `app.*` logs with the request ID attached, as in production."""
    caplog.set_level(logging.INFO, logger="app")
    caplog.handler.addFilter(RequestIdFilter())
    return caplog


def test_generates_a_request_id_when_none_is_sent(client):
    response = client.get("/health")

    request_id = response.headers[REQUEST_ID_HEADER]
    assert len(request_id) == 32
    assert request_id != client.get("/health").headers[REQUEST_ID_HEADER]


def test_reuses_a_valid_incoming_request_id(client):
    response = client.get("/health", headers={REQUEST_ID_HEADER: "abc-123.X_y"})

    assert response.headers[REQUEST_ID_HEADER] == "abc-123.X_y"


@pytest.mark.parametrize(
    "incoming",
    [
        pytest.param("has spaces", id="spaces"),
        pytest.param("a" * 65, id="too-long"),
        pytest.param("", id="empty"),
        pytest.param("x;drop", id="punctuation"),
    ],
)
def test_replaces_an_invalid_incoming_request_id(client, incoming):
    response = client.get("/health", headers={REQUEST_ID_HEADER: incoming})

    assert response.headers[REQUEST_ID_HEADER] != incoming
    assert len(response.headers[REQUEST_ID_HEADER]) == 32


def test_logs_one_line_per_request_without_the_query_string(client, request_logs):
    response = client.get("/health?token=sk-secret")

    (record,) = [r for r in request_logs.records if "HTTP request" in r.getMessage()]
    assert record.getMessage().startswith(
        "HTTP request method=GET path=/health status=200 duration_ms="
    )
    assert record.request_id == response.headers[REQUEST_ID_HEADER]
    assert "sk-secret" not in request_logs.text


def test_stream_logs_share_the_request_id(client, request_logs):
    response = client.post(
        "/api/v1/chat/stream",
        json={"message": "Hello"},
        headers={REQUEST_ID_HEADER: "stream-req-1"},
    )

    assert response.headers[REQUEST_ID_HEADER] == "stream-req-1"
    stream_summary, http_line = [
        r
        for r in request_logs.records
        if r.getMessage().startswith(("LLM stream ended", "HTTP request"))
    ]
    # The summary is logged from FastAPI's SSE task, not the route's own task,
    # yet it still sees the request's context.
    assert stream_summary.request_id == "stream-req-1"
    assert http_line.request_id == "stream-req-1"


def test_unhandled_error_is_logged_as_500(make_app, request_logs):
    app: FastAPI = make_app()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/boom").status_code == 500

    assert "HTTP request method=GET path=/boom status=500" in request_logs.text


@pytest.mark.anyio
async def test_concurrent_requests_keep_their_own_request_id():
    """Two requests interleave at an `await`; each must still see its own ID."""
    seen: dict[str, list[str | None]] = {}

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        name = scope["path"]
        seen[name] = [request_id_var.get()]
        await asyncio.sleep(0.01)  # let the other request run in between
        seen[name].append(request_id_var.get())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = RequestContextMiddleware(app)

    async def call(path: str, request_id: str) -> None:
        scope = {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [(b"x-request-id", request_id.encode())],
        }

        async def receive() -> Message:  # pragma: no cover
            return {"type": "http.request"}

        async def send(message: Message) -> None:
            pass

        await middleware(scope, receive, send)

    await asyncio.gather(call("/a", "id-a"), call("/b", "id-b"))

    assert seen == {"/a": ["id-a", "id-a"], "/b": ["id-b", "id-b"]}
    assert request_id_var.get() is None  # reset after each request


@pytest.mark.anyio
async def test_non_http_scopes_pass_through():
    calls = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        calls.append(request_id_var.get())

    async def receive() -> Message:  # pragma: no cover
        return {}

    async def send(message: Message) -> None:  # pragma: no cover
        pass

    await RequestContextMiddleware(app)({"type": "lifespan"}, receive, send)

    assert calls == [None]
