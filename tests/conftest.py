from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _forbid_env_settings() -> Settings:
    raise AssertionError(
        "Tests must not read settings from the environment or .env; "
        "use the `app` / `make_app` fixtures with explicit settings."
    )


@pytest.fixture(autouse=True)
def no_env_settings(monkeypatch):
    """Guarantee no test app is configured from a developer's local `.env`."""
    monkeypatch.setattr("app.main.get_settings", _forbid_env_settings)


@pytest.fixture
def make_app(clean_env) -> Callable[..., FastAPI]:
    """Build an app with explicit settings (mock provider unless overridden)."""

    def factory(**overrides) -> FastAPI:
        return create_app(
            Settings(_env_file=None, **{"llm_provider": "mock", **overrides})
        )

    return factory


@pytest.fixture
def app(make_app) -> FastAPI:
    return make_app()


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    # `with` runs the lifespan, which creates (and afterwards closes) the LLM service.
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def anyio_backend():
    return "asyncio"


SETTINGS_ENV_VARS = [
    "LLM_PROVIDER",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_BASE_URL",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_RETRIES",
    "LLM_SYSTEM_PROMPT",
    "LLM_TEMPERATURE",
    "LLM_MAX_OUTPUT_TOKENS",
    "LOG_LEVEL",
]


@pytest.fixture
def clean_env(monkeypatch):
    """Ignore any settings exported in the developer's shell (for Settings() tests)."""
    for name in SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
