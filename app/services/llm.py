import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    usage: LLMUsage | None = None


class LLMError(Exception):
    """Base class for provider failures. Messages are for server logs only."""


class LLMConfigurationError(LLMError):
    """The provider is missing configuration or rejected the credentials/model."""


class LLMTimeoutError(LLMError):
    """The provider did not respond within the configured timeout."""


class LLMRateLimitError(LLMError):
    """The provider is rate limiting or out of quota."""

    def __init__(self, message: str, retry_after: str | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMProviderError(LLMError):
    """Any other provider or connection failure."""


class LLMService(Protocol):
    """Interface every language-model provider must implement."""

    async def generate(self, message: str) -> LLMResult: ...


class MockLLMService:
    """Deterministic stand-in for a real model. Makes no network calls."""

    model_name = "mock-llm"

    async def generate(self, message: str) -> LLMResult:
        return LLMResult(text=f"Mock response to: {message}", model=self.model_name)


class UnconfiguredLLMService:
    """Used when the selected provider is missing configuration.

    Lets the application start (so `/health` keeps working) while every chat
    request fails with a safe configuration error.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def generate(self, message: str) -> LLMResult:
        raise LLMConfigurationError(self.reason)


def build_llm_service(settings: Settings) -> LLMService:
    if settings.llm_provider == "mock":
        logger.info("Using LLM provider=mock")
        return MockLLMService()

    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
    required = {"OPENAI_API_KEY": api_key, "OPENAI_MODEL": settings.openai_model or ""}
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        reason = f"LLM_PROVIDER=openai but required settings are missing: {', '.join(missing)}"
        logger.warning(reason)
        return UnconfiguredLLMService(reason)

    # Imported lazily so the OpenAI SDK is only loaded when it is actually used.
    from app.services.openai_llm import OpenAILLMService

    logger.info(
        "Using LLM provider=openai model=%s timeout=%ss max_retries=%s",
        settings.openai_model,
        settings.llm_timeout_seconds,
        settings.llm_max_retries,
    )
    return OpenAILLMService.from_settings(settings)


@lru_cache
def get_llm_service() -> LLMService:
    """FastAPI dependency that provides the shared LLM service."""
    return build_llm_service(get_settings())
