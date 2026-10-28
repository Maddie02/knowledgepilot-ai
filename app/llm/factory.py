"""Selects and builds the LLM provider from settings."""

import logging

from app.core.config import Settings
from app.llm.providers.mock import MockProvider
from app.llm.providers.openai import OpenAIProvider
from app.llm.providers.unconfigured import UnconfiguredProvider
from app.llm.types import LLMProvider

logger = logging.getLogger(__name__)


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "mock":
        logger.info(
            "Using LLM provider=mock chunk_delay=%ss", settings.mock_chunk_delay_seconds
        )
        return MockProvider(chunk_delay=settings.mock_chunk_delay_seconds)

    api_key = (
        settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
    )
    required = {"OPENAI_API_KEY": api_key, "OPENAI_MODEL": settings.openai_model or ""}
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        reason = f"LLM_PROVIDER=openai but required settings are missing: {', '.join(missing)}"
        logger.warning(reason)
        return UnconfiguredProvider(reason)

    logger.info(
        "Using LLM provider=openai model=%s timeout=%ss max_retries=%s",
        settings.openai_model,
        settings.llm_timeout_seconds,
        settings.llm_max_retries,
    )
    return OpenAIProvider.from_settings(settings)
