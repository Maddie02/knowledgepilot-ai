import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.exception_handlers import NOT_CONFIGURED
from app.services.llm import (
    MockLLMService,
    UnconfiguredLLMService,
    build_llm_service,
)
from app.services.openai_llm import OpenAILLMService

SECRET = "sk-should-never-appear"
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


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Ignore any provider settings exported in the developer's shell."""
    for name in SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_to_mock_provider():
    settings = Settings(_env_file=None)

    assert settings.llm_provider == "mock"
    assert isinstance(build_llm_service(settings), MockLLMService)


def test_reads_values_from_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"LLM_PROVIDER=openai\nOPENAI_API_KEY={SECRET}\nOPENAI_MODEL=some-model\n"
        "LLM_TIMEOUT_SECONDS=12.5\n"
    )

    settings = Settings(_env_file=env_file)

    assert settings.llm_provider == "openai"
    assert settings.openai_api_key.get_secret_value() == SECRET
    assert settings.openai_model == "some-model"
    assert settings.llm_timeout_seconds == 12.5


def test_api_key_is_masked_in_repr_and_serialisation():
    settings = Settings(_env_file=None, openai_api_key=SECRET)

    assert SECRET not in repr(settings)
    assert SECRET not in str(settings)
    assert SECRET not in settings.model_dump_json()


@pytest.mark.parametrize(
    ("api_key", "model", "missing"),
    [
        pytest.param(None, "some-model", "OPENAI_API_KEY", id="no-key"),
        pytest.param("   ", "some-model", "OPENAI_API_KEY", id="blank-key"),
        pytest.param(SECRET, None, "OPENAI_MODEL", id="no-model"),
    ],
)
def test_openai_without_required_config_is_unconfigured(api_key, model, missing):
    settings = Settings(
        _env_file=None, llm_provider="openai", openai_api_key=api_key, openai_model=model
    )

    service = build_llm_service(settings)

    assert isinstance(service, UnconfiguredLLMService)
    assert missing in service.reason
    assert SECRET not in service.reason


def test_unconfigured_provider_returns_safe_503_and_health_still_works(make_app):
    app = make_app(llm_provider="openai", openai_model="some-model")

    with TestClient(app) as client:
        chat = client.post("/api/v1/chat", json={"message": "hello"})
        health = client.get("/health")

    assert chat.status_code == 503
    assert chat.json() == {"detail": NOT_CONFIGURED}
    assert health.status_code == 200


def test_openai_with_full_config_builds_openai_service():
    settings = Settings(
        _env_file=None, llm_provider="openai", openai_api_key=SECRET, openai_model="some-model"
    )

    assert isinstance(build_llm_service(settings), OpenAILLMService)


@pytest.mark.parametrize(
    "overrides",
    [
        {"llm_provider": "anthropic"},
        {"llm_timeout_seconds": 0},
        {"llm_max_retries": -1},
        {"llm_temperature": 3},
        {"llm_max_output_tokens": 0},
    ],
)
def test_invalid_settings_are_rejected(overrides):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **overrides)
