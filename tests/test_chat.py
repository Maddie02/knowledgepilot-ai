import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.chat import MAX_MESSAGE_LENGTH
from app.services.llm import get_llm_service

client = TestClient(app)

CHAT_URL = "/api/v1/chat"


def test_valid_message_returns_mock_reply():
    response = client.post(CHAT_URL, json={"message": "Hello"})

    assert response.status_code == 200
    assert response.json() == {"reply": "Mock response to: Hello", "model": "mock-llm"}


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
        model_name = "fake"

        def generate(self, message: str) -> str:
            return message.upper()

    app.dependency_overrides[get_llm_service] = FakeLLMService
    try:
        response = client.post(CHAT_URL, json={"message": "hello"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"reply": "HELLO", "model": "fake"}


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
    assert "422" in operation["responses"]

    message = schemas["ChatRequest"]["properties"]["message"]
    assert message["minLength"] == 1
    assert message["maxLength"] == MAX_MESSAGE_LENGTH
    assert set(schemas["ChatResponse"]["required"]) == {"reply", "model"}
