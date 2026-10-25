"""Optional smoke test against the real provider. Costs money.

Skipped unless OPENAI_API_KEY and OPENAI_MODEL are set (env or `.env`).
Excluded from `make test`; run with `make test-live`.
"""

import pytest

from app.core.config import Settings
from app.llm.providers.openai import OpenAIProvider

pytestmark = [pytest.mark.live, pytest.mark.anyio]

settings = Settings(llm_provider="openai")
has_credentials = bool(
    settings.openai_api_key and settings.openai_api_key.get_secret_value() and settings.openai_model
)


@pytest.mark.skipif(not has_credentials, reason="OPENAI_API_KEY and OPENAI_MODEL not set")
async def test_real_provider_returns_text_and_usage():
    service = OpenAIProvider.from_settings(settings)
    try:
        result = await service.generate("Reply with the single word: pong")
    finally:
        await service.aclose()

    assert result.text.strip()
    assert result.model == settings.openai_model
    assert result.usage is None or result.usage.total_tokens > 0
