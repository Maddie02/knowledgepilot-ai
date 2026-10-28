import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_llm_provider
from app.api.exception_handlers import (
    INTERNAL_ERROR,
    NOT_CONFIGURED,
    PROVIDER_ERROR,
    TIMED_OUT,
)
from app.api.routers.chat import chat_stream
from app.llm import (
    LLMResult,
    LLMStreamEnd,
    LLMStreamEvent,
    LLMTextDelta,
    LLMTimeoutError,
    LLMUsage,
)
from app.schemas.chat import ChatRequest

STREAM_URL = "/api/v1/chat/stream"
SECRET = "sk-super-secret-value"


def parse_sse(body: str) -> list[tuple[str, Any]]:
    """Turn an SSE body into `(event, data)` pairs, skipping comment lines (pings)."""
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(
            line.split(": ", 1)
            for line in block.splitlines()
            if not line.startswith(":")
        )
        if fields:
            events.append((fields["event"], json.loads(fields["data"])))
    return events


def stream_events(client, message: str = "Hello") -> list[tuple[str, Any]]:
    response = client.post(STREAM_URL, json={"message": message})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return parse_sse(response.text)


def fake_provider(*events: LLMStreamEvent, error: Exception | None = None):
    """A provider whose stream yields `events`, then raises `error` if given."""

    class FakeProvider:
        async def stream(self, message: str) -> AsyncGenerator[LLMStreamEvent]:
            for event in events:
                yield event
            if error is not None:
                raise error

    return FakeProvider


def test_streams_mock_reply_as_deltas_then_done(client, caplog):
    caplog.set_level(logging.INFO, logger="app")

    events = stream_events(client, "Hello")

    *deltas, last = events
    assert len(deltas) > 1
    assert all(name == "delta" for name, _ in deltas)
    assert "".join(data["text"] for _, data in deltas) == "Mock response to: Hello"
    assert last == ("done", {"model": "mock-llm", "usage": None})
    assert "LLM stream ended outcome=completed deltas=4 error=None" in caplog.text


def test_done_event_carries_usage(app, client):
    app.dependency_overrides[get_llm_provider] = fake_provider(
        LLMTextDelta(text="Hi"),
        LLMStreamEnd(
            model="fake",
            usage=LLMUsage(input_tokens=3, output_tokens=2, total_tokens=5),
        ),
    )

    assert stream_events(client) == [
        ("delta", {"text": "Hi"}),
        (
            "done",
            {
                "model": "fake",
                "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            },
        ),
    ]


def test_invalid_body_is_rejected_before_streaming(client):
    response = client.post(STREAM_URL, json={"message": "   "})

    assert response.status_code == 422


def test_failure_before_first_delta_is_an_error_event(make_app):

    app = make_app(llm_provider="openai", openai_model="some-model")  # no API key

    with TestClient(app) as client:
        events = stream_events(client)

    assert events == [("error", {"detail": NOT_CONFIGURED})]


def test_mid_stream_failure_keeps_deltas_and_ends_with_error(app, client, caplog):
    app.dependency_overrides[get_llm_provider] = fake_provider(
        LLMTextDelta(text="Partial "),
        error=LLMTimeoutError(f"timeout {SECRET}"),
    )
    caplog.set_level(logging.DEBUG, logger="app")

    response = client.post(STREAM_URL, json={"message": "Hello"})

    assert parse_sse(response.text) == [
        ("delta", {"text": "Partial "}),
        ("error", {"detail": TIMED_OUT}),
    ]
    assert "LLM stream ended outcome=failed deltas=1 error=LLMTimeoutError" in (
        caplog.text
    )
    assert SECRET not in response.text
    assert SECRET not in caplog.text


def test_stream_without_text_is_a_provider_error(app, client):
    app.dependency_overrides[get_llm_provider] = fake_provider(
        LLMStreamEnd(model="fake")
    )

    assert stream_events(client) == [("error", {"detail": PROVIDER_ERROR})]


def test_unexpected_exception_is_a_safe_error_event(app, client, caplog):
    app.dependency_overrides[get_llm_provider] = fake_provider(
        error=RuntimeError(SECRET)
    )

    events = stream_events(client)

    assert events == [("error", {"detail": INTERNAL_ERROR})]
    assert SECRET not in json.dumps(events)
    assert "Unexpected error while streaming" in caplog.text


def test_openapi_documents_stream_endpoint(client):
    spec = client.get("/openapi.json").json()
    operation = spec["paths"][STREAM_URL]["post"]

    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ChatRequest"
    }
    assert "text/event-stream" in operation["responses"]["200"]["content"]
    assert "422" in operation["responses"]


class EndlessProvider:
    """Streams one delta, then waits forever, like a slow model. Records cleanup."""

    def __init__(self) -> None:
        self.closed = False

    async def stream(self, message: str) -> AsyncGenerator[LLMStreamEvent]:
        try:
            yield LLMTextDelta(text="Partial ")
            await asyncio.Event().wait()  # never set
            yield LLMStreamEnd(model="never")  # pragma: no cover
        finally:
            self.closed = True

    async def generate(self, message: str) -> LLMResult:  # pragma: no cover
        raise AssertionError("not used by the streaming route")

    async def aclose(self) -> None:  # pragma: no cover
        pass


# The tests below drive the route generator directly: that is what FastAPI does,
# and it lets us stop it exactly where a client disconnect would.


@pytest.mark.anyio
async def test_closing_the_stream_closes_the_provider_and_logs_cancelled(caplog):
    caplog.set_level(logging.INFO, logger="app")
    provider = EndlessProvider()
    stream = chat_stream(ChatRequest(message="Hi"), provider)

    first = await anext(stream)
    await stream.aclose()  # what happens to a stream paused at `yield`

    assert first.event == "delta"
    assert provider.closed  # immediately, not at garbage collection
    assert "LLM stream ended outcome=cancelled deltas=1 error=None" in caplog.text


@pytest.mark.anyio
async def test_cancelling_while_waiting_for_the_provider_propagates(caplog):
    caplog.set_level(logging.INFO, logger="app")
    provider = EndlessProvider()
    received = []

    async def consume() -> None:
        async for event in chat_stream(ChatRequest(message="Hi"), provider):
            received.append(event.event)

    task = asyncio.create_task(consume())
    while not received:  # wait until the first delta arrived
        await asyncio.sleep(0)
    task.cancel()  # what a client disconnect does to the task running the stream

    with pytest.raises(asyncio.CancelledError):
        await task  # re-raised, not swallowed or turned into an `error` event

    assert received == ["delta"]
    assert provider.closed
    assert "LLM stream ended outcome=cancelled deltas=1 error=None" in caplog.text
