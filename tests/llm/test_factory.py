import pytest

from app.core.config import Settings
from app.llm import build_llm_provider
from app.llm.providers.mock import MockProvider
from app.llm.providers.openai import OpenAIProvider
from app.llm.providers.unconfigured import UnconfiguredProvider

SECRET = "sk-should-never-appear"

pytestmark = pytest.mark.usefixtures("clean_env")


def test_mock_provider_is_the_default():
    assert isinstance(build_llm_provider(Settings(_env_file=None)), MockProvider)


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

    provider = build_llm_provider(settings)

    assert isinstance(provider, UnconfiguredProvider)
    assert missing in provider.reason
    assert SECRET not in provider.reason


@pytest.mark.anyio
async def test_openai_with_full_config_builds_openai_provider():
    settings = Settings(
        _env_file=None, llm_provider="openai", openai_api_key=SECRET, openai_model="some-model"
    )

    provider = build_llm_provider(settings)
    try:
        assert isinstance(provider, OpenAIProvider)
    finally:
        await provider.aclose()
