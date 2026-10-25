"""OpenAI provider. The only module that imports the `openai` SDK.

Note: `from openai import ...` below loads the installed SDK, not this file -
Python 3 imports are absolute, and this module's own name is `app.llm.providers.openai`.
"""

import logging
import time
from typing import Any

from openai import (
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    NotFoundError,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
)

from app.core.config import Settings
from app.llm.errors import (
    LLMConfigurationError,
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.llm.types import LLMResult, LLMUsage

logger = logging.getLogger(__name__)


class OpenAIProvider:
    """LLM provider backed by the OpenAI Responses API."""

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        system_prompt: str,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._system_prompt = system_prompt
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAIProvider":
        if settings.openai_api_key is None or not settings.openai_model:
            raise LLMConfigurationError("OpenAI API key and model must be configured")

        client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            base_url=settings.openai_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
        return cls(
            client=client,
            model=settings.openai_model,
            system_prompt=settings.llm_system_prompt,
            temperature=settings.llm_temperature,
            max_output_tokens=settings.llm_max_output_tokens,
        )

    async def generate(self, message: str) -> LLMResult:
        params: dict[str, Any] = {
            "model": self._model,
            "instructions": self._system_prompt,
            "input": message,
        }
        if self._temperature is not None:
            params["temperature"] = self._temperature
        if self._max_output_tokens is not None:
            params["max_output_tokens"] = self._max_output_tokens

        started = time.perf_counter()
        try:
            response = await self._client.responses.create(**params)
        except OpenAIError as exc:
            raise self._translate_error(exc) from None
        latency_ms = (time.perf_counter() - started) * 1000

        text = response.output_text
        if not text:
            logger.warning(
                "LLM returned no text (status=%s)", getattr(response, "status", None)
            )
            raise LLMProviderError("Provider returned an empty response")

        usage = None
        if response.usage is not None:
            usage = LLMUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                total_tokens=response.usage.total_tokens,
            )

        logger.info(
            "LLM request completed model=%s latency_ms=%.0f input_tokens=%s output_tokens=%s",
            self._model,
            latency_ms,
            usage.input_tokens if usage else None,
            usage.output_tokens if usage else None,
        )
        return LLMResult(text=text, model=self._model, usage=usage)

    async def aclose(self) -> None:
        await self._client.close()

    @staticmethod
    def _translate_error(exc: OpenAIError) -> LLMError:
        """Map SDK errors to provider-neutral errors.

        Only the exception type, status code and request ID are logged: SDK
        messages can contain request details and (masked) credentials.
        """
        status_code = getattr(exc, "status_code", None)
        request_id = getattr(exc, "request_id", None)
        logger.warning(
            "LLM request failed error=%s status_code=%s request_id=%s",
            type(exc).__name__,
            status_code,
            request_id,
        )

        if isinstance(exc, APITimeoutError):
            return LLMTimeoutError("Provider request timed out")
        if isinstance(exc, (AuthenticationError, PermissionDeniedError, NotFoundError)):
            return LLMConfigurationError(
                f"Provider rejected configuration ({status_code})"
            )
        if isinstance(exc, RateLimitError):
            return LLMRateLimitError(
                "Provider rate limit reached",
                retry_after=exc.response.headers.get("retry-after"),
            )
        if isinstance(exc, APIStatusError):
            return LLMProviderError(f"Provider returned status {status_code}")
        return LLMProviderError(f"Provider request failed ({type(exc).__name__})")
