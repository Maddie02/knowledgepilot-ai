"""Tests for OpenAILLMService.

Requests go through the real `AsyncOpenAI` client, but its HTTP transport is
replaced with `MockTransport`, so nothing leaves the machine and nothing is billed.
"""

import json
import logging

import httpx2
import pytest
from openai import AsyncOpenAI

from app.config import Settings
from app.services.llm import (
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUsage,
)
from app.services.openai_llm import OpenAILLMService

pytestmark = pytest.mark.anyio

API_KEY = "sk-test-secret-key"
MODEL = "test-model"
SYSTEM_PROMPT = "You are a test assistant."


def response_body(text: str = "Hello there", usage: dict | None = None) -> dict:
    body = {
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


def make_service(handler, **kwargs) -> OpenAILLMService:
    client = AsyncOpenAI(
        api_key=API_KEY,
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    return OpenAILLMService(client=client, model=MODEL, system_prompt=SYSTEM_PROMPT, **kwargs)


def error_handler(status_code: int, headers: dict | None = None):
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

    result = await make_service(handler).generate("Hi")

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

    await make_service(handler, temperature=0.2, max_output_tokens=100).generate("Hi")

    assert payloads[0]["temperature"] == 0.2
    assert payloads[0]["max_output_tokens"] == 100


async def test_usage_is_none_when_provider_omits_it():
    service = make_service(lambda request: httpx2.Response(200, json=response_body()))

    result = await service.generate("Hi")

    assert result.usage is None


async def test_empty_output_is_a_provider_error():
    service = make_service(lambda request: httpx2.Response(200, json=response_body(text="")))

    with pytest.raises(LLMProviderError):
        await service.generate("Hi")


async def test_timeout_maps_to_timeout_error():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timed out", request=request)

    with pytest.raises(LLMTimeoutError):
        await make_service(handler).generate("Hi")


async def test_connection_failure_maps_to_provider_error():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    with pytest.raises(LLMProviderError):
        await make_service(handler).generate("Hi")


@pytest.mark.parametrize("status_code", [401, 403, 404])
async def test_rejected_credentials_or_model_map_to_configuration_error(status_code):
    with pytest.raises(LLMConfigurationError):
        await make_service(error_handler(status_code)).generate("Hi")


async def test_rate_limit_maps_to_rate_limit_error_with_retry_after():
    service = make_service(error_handler(429, headers={"retry-after": "7"}))

    with pytest.raises(LLMRateLimitError) as exc_info:
        await service.generate("Hi")

    assert exc_info.value.retry_after == "7"


@pytest.mark.parametrize("status_code", [400, 500, 503])
async def test_other_status_errors_map_to_provider_error(status_code):
    with pytest.raises(LLMProviderError):
        await make_service(error_handler(status_code)).generate("Hi")


async def test_errors_do_not_leak_api_key(caplog):
    caplog.set_level(logging.DEBUG, logger="app")

    with pytest.raises(LLMConfigurationError) as exc_info:
        await make_service(error_handler(401)).generate("Hi")

    assert API_KEY not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert "error=AuthenticationError status_code=401" in caplog.text
    assert API_KEY not in caplog.text


async def test_success_logs_latency_and_token_usage(caplog):
    caplog.set_level(logging.INFO, logger="app")
    service = make_service(lambda request: httpx2.Response(200, json=response_body(usage=USAGE)))

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

    service = OpenAILLMService.from_settings(settings)
    try:
        assert service._client.timeout == 5
        assert service._client.max_retries == 1
        assert str(service._client.base_url).startswith("https://llm.example.com/v1")
    finally:
        await service.aclose()
