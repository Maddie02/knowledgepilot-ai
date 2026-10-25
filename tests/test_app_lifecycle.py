"""Tests for application-owned resources (lifespan + app.state)."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies import get_llm_service
from app.main import create_app
from app.services.llm import LLMResult, MockLLMService
from app.services.openai_llm import OpenAILLMService


class TrackingLLMService:
    def __init__(self) -> None:
        self.closed = False

    async def generate(self, message: str) -> LLMResult:
        return LLMResult(text="tracked", model="tracking")

    async def aclose(self) -> None:
        self.closed = True


def test_lifespan_builds_service_from_explicit_settings(app):
    with TestClient(app):
        assert isinstance(app.state.llm_service, MockLLMService)
        assert app.state.settings.llm_provider == "mock"


def test_each_app_owns_its_own_service(make_app):
    first, second = make_app(), make_app()

    with TestClient(first), TestClient(second):
        assert first.state.llm_service is not second.state.llm_service


def test_shutdown_closes_the_service(make_app, monkeypatch):
    service = TrackingLLMService()
    monkeypatch.setattr("app.main.build_llm_service", lambda settings: service)
    app = make_app()

    with TestClient(app) as client:
        assert client.post("/api/v1/chat", json={"message": "hi"}).json()["reply"] == "tracked"
        assert not service.closed

    assert service.closed


def test_shutdown_closes_openai_http_client(make_app):
    # Builds a real OpenAI client (no request is sent) to check its pool is closed.
    app = make_app(llm_provider="openai", openai_api_key="sk-test", openai_model="m")

    with TestClient(app):
        service = app.state.llm_service
        assert isinstance(service, OpenAILLMService)
        assert not service._client.is_closed()

    assert service._client.is_closed()


def test_dependency_override_takes_precedence(app):
    app.dependency_overrides[get_llm_service] = TrackingLLMService

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"message": "hi"})

    assert response.json()["model"] == "tracking"


def test_default_app_reads_settings_at_startup_not_import(monkeypatch):
    calls = []

    def fake_get_settings() -> Settings:
        calls.append(1)
        return Settings(_env_file=None, llm_provider="mock")

    monkeypatch.setattr("app.main.get_settings", fake_get_settings)
    app = create_app()
    assert calls == []  # building the app reads nothing

    with TestClient(app):
        assert calls == [1]  # settings are resolved once, at startup
