import pytest
from fastapi.testclient import TestClient

from app.exception_handlers import BUSY, NOT_CONFIGURED, PROVIDER_ERROR, TIMED_OUT
from app.main import app
from app.schemas.chat import MAX_MESSAGE_LENGTH
from app.services.llm import (
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResult,
    LLMTimeoutError,
    LLMUsage,
    get_llm_service,
)

client = TestClient(app)

CHAT_URL = "/api/v1/chat"


def test_valid_message_returns_mock_reply():
    response = client.post(CHAT_URL, json={"message": "Hello"})

    assert response.status_code == 200
    assert response.json() == {
        "reply": "Mock response to: Hello",
        "model": "mock-llm",
        "usage": None,
    }


def test_reply_is_deterministic():
    first = client.post(CHAT_URL, json={"message": "Same question"})
    second = client.post(CHAT_URL, json={"message": "Same question"})

    assert first.json() == second.json()


def test_surrounding_whitespace_is_stripped():
    response = client.post(CHAT_URL, json={"message": "  Hello  "})

    assert response.status_code == 200
    assert response.json()["reply"] == "Mock response to: Hello"


def test_message_at_max_length_is_accepted():
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
def test_invalid_body_is_rejected(body):
    response = client.post(CHAT_URL, json=body)

    assert response.status_code == 422
    assert "detail" in response.json()


def test_malformed_json_is_rejected():
    response = client.post(
        CHAT_URL,
        content='{"message": ',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422


def test_route_delegates_to_injected_service():
    class FakeLLMService:
        async def generate(self, message: str) -> LLMResult:
            return LLMResult(
                text=message.upper(),
                model="fake",
                usage=LLMUsage(input_tokens=3, output_tokens=2, total_tokens=5),
            )

    app.dependency_overrides[get_llm_service] = FakeLLMService

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
def test_provider_errors_map_to_safe_responses(error, expected_status, expected_detail):
    class FailingLLMService:
        async def generate(self, message: str) -> LLMResult:
            raise error

    app.dependency_overrides[get_llm_service] = FailingLLMService

    response = client.post(CHAT_URL, json={"message": "hello"})

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert SECRET not in response.text


def test_rate_limit_forwards_retry_after():
    class RateLimitedLLMService:
        async def generate(self, message: str) -> LLMResult:
            raise LLMRateLimitError("429", retry_after="20")

    app.dependency_overrides[get_llm_service] = RateLimitedLLMService

    response = client.post(CHAT_URL, json={"message": "hello"})

    assert response.status_code == 503
    assert response.headers["retry-after"] == "20"


def test_openapi_documents_chat_schemas():
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
