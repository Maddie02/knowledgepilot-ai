import logging

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_llm_provider
from app.core.exception_handlers import BUSY, NOT_CONFIGURED, PROVIDER_ERROR, TIMED_OUT
from app.llm import (
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResult,
    LLMTimeoutError,
    LLMUsage,
)
from app.schemas.chat import MAX_MESSAGE_LENGTH

CHAT_URL = "/api/v1/chat"


def test_valid_message_returns_mock_reply(client):
    response = client.post(CHAT_URL, json={"message": "Hello"})

    assert response.status_code == 200
    assert response.json() == {
        "reply": "Mock response to: Hello",
        "model": "mock-llm",
        "usage": None,
    }


def test_reply_is_deterministic(client):
    first = client.post(CHAT_URL, json={"message": "Same question"})
    second = client.post(CHAT_URL, json={"message": "Same question"})

    assert first.json() == second.json()


def test_surrounding_whitespace_is_stripped(client):
    response = client.post(CHAT_URL, json={"message": "  Hello  "})

    assert response.status_code == 200
    assert response.json()["reply"] == "Mock response to: Hello"


def test_message_at_max_length_is_accepted(client):
    response = client.post(CHAT_URL, json={"message": "a" * MAX_MESSAGE_LENGTH})

    assert response.status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"message": ""}, id="empty"),
        pytest.param({"message": "   \n\t "}, id="whitespace-only"),
        pytest.param({"message": "a" * (MAX_MESSAGE_LENGTH + 1)}, id="too-long"),
        pytest.param({}, id="missing-message"),
        pytest.param({"message": 123}, id="wrong-type"),
        pytest.param({"message": None}, id="null"),
        pytest.param({"message": "Hi", "extra": "x"}, id="unknown-field"),
    ],
)
def test_invalid_body_is_rejected(body, client):
    response = client.post(CHAT_URL, json=body)

    assert response.status_code == 422
    assert "detail" in response.json()


def test_malformed_json_is_rejected(client):
    response = client.post(
        CHAT_URL,
        content='{"message": ',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422


def test_route_delegates_to_injected_service(app, client):
    class FakeProvider:
        async def generate(self, message: str) -> LLMResult:
            return LLMResult(
                text=message.upper(),
                model="fake",
                usage=LLMUsage(input_tokens=3, output_tokens=2, total_tokens=5),
            )

    app.dependency_overrides[get_llm_provider] = FakeProvider

    response = client.post(CHAT_URL, json={"message": "hello"})

    assert response.status_code == 200
    assert response.json() == {
        "reply": "HELLO",
        "model": "fake",
        "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
    }


SECRET = "sk-super-secret-value"


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        pytest.param(
            LLMConfigurationError(f"bad key {SECRET}"), 503, NOT_CONFIGURED, id="configuration"
        ),
        pytest.param(LLMTimeoutError(f"timeout {SECRET}"), 504, TIMED_OUT, id="timeout"),
        pytest.param(LLMRateLimitError(f"429 {SECRET}"), 503, BUSY, id="rate-limit"),
        pytest.param(LLMProviderError(f"500 {SECRET}"), 502, PROVIDER_ERROR, id="provider"),
    ],
)
def test_provider_errors_map_to_safe_responses_and_logs(
    error, expected_status, expected_detail, app, client, caplog
):
    class FailingProvider:
        async def generate(self, message: str) -> LLMResult:
            raise error

    app.dependency_overrides[get_llm_provider] = FailingProvider
    caplog.set_level(logging.DEBUG, logger="app")

    response = client.post(CHAT_URL, json={"message": "hello"})

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert SECRET not in response.text

    # Logs carry controlled metadata only - never the exception message.
    assert (
        f"LLM request failed method=POST path={CHAT_URL} "
        f"error={type(error).__name__} status_code={expected_status}"
    ) in caplog.text
    assert SECRET not in caplog.text


def test_rate_limit_forwards_retry_after(app, client):
    class RateLimitedProvider:
        async def generate(self, message: str) -> LLMResult:
            raise LLMRateLimitError("429", retry_after="20")

    app.dependency_overrides[get_llm_provider] = RateLimitedProvider

    response = client.post(CHAT_URL, json={"message": "hello"})

    assert response.status_code == 503
    assert response.headers["retry-after"] == "20"


def test_openapi_documents_chat_schemas(client):
    spec = client.get("/openapi.json").json()
    operation = spec["paths"][CHAT_URL]["post"]
    schemas = spec["components"]["schemas"]

    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ChatRequest"
    }
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ChatResponse"
    }
    assert {"422", "502", "503", "504"} <= set(operation["responses"])

    message = schemas["ChatRequest"]["properties"]["message"]
    assert message["minLength"] == 1
    assert message["maxLength"] == MAX_MESSAGE_LENGTH
    assert set(schemas["ChatResponse"]["required"]) == {"reply", "model"}
    assert "usage" in schemas["ChatResponse"]["properties"]
    assert set(schemas["TokenUsage"]["required"]) == {
        "input_tokens",
        "output_tokens",
        "total_tokens",
    }


def test_unconfigured_provider_returns_safe_503_and_health_still_works(make_app):
    app = make_app(llm_provider="openai", openai_model="some-model")  # no API key

    with TestClient(app) as client:
        chat = client.post(CHAT_URL, json={"message": "hello"})
        health = client.get("/health")

    assert chat.status_code == 503
    assert chat.json() == {"detail": NOT_CONFIGURED}
    assert health.status_code == 200
