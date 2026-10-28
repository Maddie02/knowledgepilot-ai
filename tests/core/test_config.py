import pytest

from app.core.config import Settings

SECRET = "sk-should-never-appear"

pytestmark = pytest.mark.usefixtures("clean_env")


def test_defaults():
    settings = Settings(_env_file=None)

    assert settings.llm_provider == "mock"
    assert settings.openai_api_key is None
    assert settings.log_level == "INFO"


def test_reads_values_from_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"LLM_PROVIDER=openai\nOPENAI_API_KEY={SECRET}\nOPENAI_MODEL=some-model\n"
        "LLM_TIMEOUT_SECONDS=12.5\n"
    )

    settings = Settings(_env_file=env_file)

    assert settings.llm_provider == "openai"
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == SECRET
    assert settings.openai_model == "some-model"
    assert settings.llm_timeout_seconds == 12.5


def test_api_key_is_masked_in_repr_and_serialisation():
    settings = Settings(_env_file=None, openai_api_key=SECRET)

    assert SECRET not in repr(settings)
    assert SECRET not in str(settings)
    assert SECRET not in settings.model_dump_json()


@pytest.mark.parametrize(
    "overrides",
    [
        {"llm_provider": "anthropic"},
        {"llm_timeout_seconds": 0},
        {"llm_max_retries": -1},
        {"llm_temperature": 3},
        {"llm_max_output_tokens": 0},
        {"log_level": "LOUD"},
        {"mock_chunk_delay_seconds": -1},
    ],
)
def test_invalid_settings_are_rejected(overrides):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **overrides)
