"""Tests for application-owned resources (lifespan + app.state)."""

from fastapi.testclient import TestClient

from app.api.dependencies import get_llm_provider
from app.core.config import Settings
from app.llm import LLMResult
from app.llm.providers.mock import MockProvider
from app.llm.providers.openai import OpenAIProvider
from app.main import create_app


class TrackingProvider:
    def __init__(self) -> None:
        self.closed = False

    async def generate(self, message: str) -> LLMResult:
        return LLMResult(text="tracked", model="tracking")

    async def aclose(self) -> None:
        self.closed = True


def test_lifespan_builds_provider_from_explicit_settings(app):
    with TestClient(app):
        assert isinstance(app.state.llm_provider, MockProvider)
        assert app.state.settings.llm_provider == "mock"


def test_each_app_owns_its_own_provider(make_app):
    first, second = make_app(), make_app()

    with TestClient(first), TestClient(second):
        assert first.state.llm_provider is not second.state.llm_provider


def test_shutdown_closes_the_provider(make_app, monkeypatch):
    provider = TrackingProvider()
    monkeypatch.setattr("app.main.build_llm_provider", lambda settings: provider)
    app = make_app()

    with TestClient(app) as client:
        assert client.post("/api/v1/chat", json={"message": "hi"}).json()["reply"] == "tracked"
        assert not provider.closed

    assert provider.closed


def test_shutdown_closes_openai_http_client(make_app):
    # Builds a real OpenAI client (no request is sent) to check its pool is closed.
    app = make_app(llm_provider="openai", openai_api_key="sk-test", openai_model="m")

    with TestClient(app):
        provider = app.state.llm_provider
        assert isinstance(provider, OpenAIProvider)
        assert not provider._client.is_closed()

    assert provider._client.is_closed()


def test_dependency_override_takes_precedence(app):
    app.dependency_overrides[get_llm_provider] = TrackingProvider

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
