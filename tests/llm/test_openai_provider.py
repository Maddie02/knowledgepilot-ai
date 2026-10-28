"""Tests for OpenAIProvider.

Requests go through the real `AsyncOpenAI` client, but its HTTP transport is
replaced with `MockTransport`, so nothing leaves the machine and nothing is billed.
"""

import json
import logging
from typing import Any

import httpx2
import pytest
from openai import AsyncOpenAI

from app.core.config import Settings
from app.llm import (
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMStreamEnd,
    LLMTextDelta,
    LLMTimeoutError,
    LLMUsage,
)
from app.llm.providers.openai import OpenAIProvider
from tests.llm.stream_utils import collect_stream

pytestmark = pytest.mark.anyio

API_KEY = "sk-test-secret-key"
MODEL = "test-model"
SYSTEM_PROMPT = "You are a test assistant."


def response_body(
    text: str = "Hello there", usage: dict[str, Any] | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "resp_123",
        "object": "response",
        "created_at": 0,
        "model": f"{MODEL}-2026-01-01",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "id": "msg_123",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
    }
    if usage is not None:
        body["usage"] = usage
    return body


USAGE = {
    "input_tokens": 12,
    "output_tokens": 5,
    "total_tokens": 17,
    "input_tokens_details": {"cached_tokens": 0},
    "output_tokens_details": {"reasoning_tokens": 0},
}


def make_provider(handler, **kwargs) -> OpenAIProvider:
    client = AsyncOpenAI(
        api_key=API_KEY,
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    return OpenAIProvider(
        client=client, model=MODEL, system_prompt=SYSTEM_PROMPT, **kwargs
    )


def error_handler(status_code: int, headers: dict[str, str] | None = None):
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status_code,
            headers=headers,
            json={"error": {"message": f"Incorrect API key provided: {API_KEY}"}},
        )

    return handler


async def test_returns_text_configured_model_and_usage():
    requests = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json=response_body(usage=USAGE))

    result = await make_provider(handler).generate("Hi")

    assert result.text == "Hello there"
    assert result.model == MODEL
    assert result.usage == LLMUsage(input_tokens=12, output_tokens=5, total_tokens=17)

    (request,) = requests
    assert request.url.path.endswith("/responses")
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    assert json.loads(request.content) == {
        "model": MODEL,
        "instructions": SYSTEM_PROMPT,
        "input": "Hi",
    }


async def test_sends_optional_inference_parameters():
    payloads = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        payloads.append(json.loads(request.content))
        return httpx2.Response(200, json=response_body(usage=USAGE))

    await make_provider(handler, temperature=0.2, max_output_tokens=100).generate("Hi")

    assert payloads[0]["temperature"] == 0.2
    assert payloads[0]["max_output_tokens"] == 100


async def test_usage_is_none_when_provider_omits_it():
    service = make_provider(lambda request: httpx2.Response(200, json=response_body()))

    result = await service.generate("Hi")

    assert result.usage is None


async def test_empty_output_is_a_provider_error():
    service = make_provider(
        lambda request: httpx2.Response(200, json=response_body(text=""))
    )

    with pytest.raises(LLMProviderError):
        await service.generate("Hi")


async def test_timeout_maps_to_timeout_error():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timed out", request=request)

    with pytest.raises(LLMTimeoutError):
        await make_provider(handler).generate("Hi")


async def test_connection_failure_maps_to_provider_error():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    with pytest.raises(LLMProviderError):
        await make_provider(handler).generate("Hi")


@pytest.mark.parametrize("status_code", [401, 403, 404])
async def test_rejected_credentials_or_model_map_to_configuration_error(status_code):
    with pytest.raises(LLMConfigurationError):
        await make_provider(error_handler(status_code)).generate("Hi")


async def test_rate_limit_maps_to_rate_limit_error_with_retry_after():
    service = make_provider(error_handler(429, headers={"retry-after": "7"}))

    with pytest.raises(LLMRateLimitError) as exc_info:
        await service.generate("Hi")

    assert exc_info.value.retry_after == "7"


@pytest.mark.parametrize("status_code", [400, 500, 503])
async def test_other_status_errors_map_to_provider_error(status_code):
    with pytest.raises(LLMProviderError):
        await make_provider(error_handler(status_code)).generate("Hi")


async def test_errors_do_not_leak_api_key(caplog):
    caplog.set_level(logging.DEBUG, logger="app")

    with pytest.raises(LLMConfigurationError) as exc_info:
        await make_provider(error_handler(401)).generate("Hi")

    assert API_KEY not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert "error=AuthenticationError status_code=401" in caplog.text
    assert API_KEY not in caplog.text


async def test_success_logs_latency_and_token_usage(caplog):
    caplog.set_level(logging.INFO, logger="app")
    service = make_provider(
        lambda request: httpx2.Response(200, json=response_body(usage=USAGE))
    )

    await service.generate("Hi")

    (record,) = [r for r in caplog.records if "LLM request completed" in r.getMessage()]
    message = record.getMessage()
    assert f"model={MODEL}" in message
    assert "latency_ms=" in message
    assert "input_tokens=12 output_tokens=5" in message


async def test_from_settings_applies_timeout_retries_and_base_url():
    settings = Settings(
        _env_file=None,
        llm_provider="openai",
        openai_api_key=API_KEY,
        openai_model=MODEL,
        openai_base_url="https://llm.example.com/v1",
        llm_timeout_seconds=5,
        llm_max_retries=1,
    )

    service = OpenAIProvider.from_settings(settings)
    try:
        assert service._client.timeout == 5
        assert service._client.max_retries == 1
        assert str(service._client.base_url).startswith("https://llm.example.com/v1")
    finally:
        await service.aclose()


async def test_stream_raises_translated_errors_on_first_read():
    provider = make_provider(error_handler(429))
    stream = provider.stream("Hi")

    with pytest.raises(LLMRateLimitError):
        await anext(stream)


# --- Streaming -------------------------------------------------------------
# OpenAI streams Server-Sent Events, just like our own endpoint. These helpers
# build such a body so the real SDK parses it, without any network call.


def sse_body(*events: dict[str, Any]) -> bytes:
    return b"".join(
        f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()
        for event in events
    )


def text_delta(text: str) -> dict[str, Any]:
    return {
        "type": "response.output_text.delta",
        "item_id": "msg_123",
        "output_index": 0,
        "content_index": 0,
        "delta": text,
        "logprobs": [],
        "sequence_number": 1,
    }


def final_event(event_type: str, **response_fields: Any) -> dict[str, Any]:
    """`response.completed` / `.incomplete` / `.failed` with a full response."""
    return {
        "type": event_type,
        "response": {**response_body(usage=USAGE), **response_fields},
        "sequence_number": 99,
    }


def stream_handler(*events: dict[str, Any], requests: list[Any] | None = None):
    def handler(request: httpx2.Request) -> httpx2.Response:
        if requests is not None:
            requests.append(request)
        return httpx2.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=sse_body(*events),
        )

    return handler


async def test_stream_yields_text_deltas_then_end_with_usage():
    requests: list[httpx2.Request] = []
    provider = make_provider(
        stream_handler(
            {"type": "response.created", "sequence_number": 0},  # ignored
            text_delta("Hello"),
            text_delta(""),  # empty deltas are skipped
            text_delta(" there"),
            final_event("response.completed"),
            requests=requests,
        )
    )

    texts, end = await collect_stream(provider.stream("Hi"))

    assert texts == ["Hello", " there"]
    assert end == LLMStreamEnd(
        model=MODEL,
        usage=LLMUsage(input_tokens=12, output_tokens=5, total_tokens=17),
    )
    (request,) = requests
    assert json.loads(request.content) == {
        "model": MODEL,
        "instructions": SYSTEM_PROMPT,
        "input": "Hi",
        "stream": True,
    }


async def test_incomplete_stream_still_ends_normally(caplog):
    caplog.set_level(logging.WARNING, logger="app")
    provider = make_provider(
        stream_handler(
            text_delta("Partial"),
            final_event(
                "response.incomplete",
                status="incomplete",
                incomplete_details={"reason": "max_output_tokens"},
            ),
        )
    )

    texts, end = await collect_stream(provider.stream("Hi"))

    assert texts == ["Partial"]
    assert end.model == MODEL
    assert "LLM stream incomplete reason=max_output_tokens" in caplog.text


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(
            final_event(
                "response.failed",
                status="failed",
                error={"code": "server_error", "message": f"boom {API_KEY}"},
            ),
            id="response.failed",
        ),
        pytest.param(
            {
                "type": "error",
                "code": "server_error",
                "message": f"boom {API_KEY}",
                "param": None,
                "sequence_number": 2,
            },
            id="error",
        ),
    ],
)
async def test_failure_event_mid_stream_raises_provider_error(failure, caplog):
    caplog.set_level(logging.DEBUG, logger="app")
    stream = make_provider(stream_handler(text_delta("Partial"), failure)).stream("Hi")

    assert await anext(stream) == LLMTextDelta(text="Partial")
    with pytest.raises(LLMProviderError) as exc_info:
        await anext(stream)

    assert f"event={failure['type']}" in caplog.text
    assert API_KEY not in caplog.text
    assert API_KEY not in str(exc_info.value)


async def test_stream_cut_off_without_final_event_raises_provider_error():
    stream = make_provider(stream_handler(text_delta("Partial"))).stream("Hi")

    assert await anext(stream) == LLMTextDelta(text="Partial")
    with pytest.raises(LLMProviderError):
        await anext(stream)


async def test_timeout_mid_stream_maps_to_timeout_error():
    class TimesOutAfterOneEvent(httpx2.AsyncByteStream):
        async def __aiter__(self):
            yield sse_body(text_delta("Partial"))
            raise httpx2.ReadTimeout("timed out")

    provider = make_provider(
        lambda request: httpx2.Response(200, stream=TimesOutAfterOneEvent())
    )
    stream = provider.stream("Hi")

    assert await anext(stream) == LLMTextDelta(text="Partial")
    with pytest.raises(LLMTimeoutError):
        await anext(stream)


async def test_closing_the_stream_early_closes_the_http_response():
    class TrackedBody(httpx2.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield sse_body(text_delta("Hello"), text_delta(" there"))

        async def aclose(self) -> None:
            self.closed = True

    body = TrackedBody()
    provider = make_provider(lambda request: httpx2.Response(200, stream=body))
    stream = provider.stream("Hi")

    await anext(stream)
    await stream.aclose()  # what our route does when the client disconnects

    assert body.closed
