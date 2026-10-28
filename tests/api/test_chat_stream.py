import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastapi.testclient import TestClient

from app.api.dependencies import get_llm_provider
from app.api.exception_handlers import (
    INTERNAL_ERROR,
    NOT_CONFIGURED,
    PROVIDER_ERROR,
    TIMED_OUT,
)
from app.llm import (
    LLMStreamEnd,
    LLMStreamEvent,
    LLMTextDelta,
    LLMTimeoutError,
    LLMUsage,
)

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


def test_streams_mock_reply_as_deltas_then_done(client):
    events = stream_events(client, "Hello")

    *deltas, last = events
    assert len(deltas) > 1
    assert all(name == "delta" for name, _ in deltas)
    assert "".join(data["text"] for _, data in deltas) == "Mock response to: Hello"
    assert last == ("done", {"model": "mock-llm", "usage": None})


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
    assert "LLM stream failed error=LLMTimeoutError" in caplog.text
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
