from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SYSTEM_PROMPT = (
    "You are KnowledgePilot, a helpful assistant for company employees. "
    "Answer clearly and concisely. If you do not know the answer, say so "
    "instead of guessing."
)


class Settings(BaseSettings):
    """Application settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: Literal["mock", "openai"] = Field(
        default="mock",
        description="Which LLM backend to use. `mock` needs no credentials.",
    )

    openai_api_key: SecretStr | None = Field(
        default=None,
        description="OpenAI API key. Never logged or returned to clients.",
    )
    openai_model: str | None = Field(
        default=None,
        description="Model ID to request from the provider.",
    )
    openai_base_url: str | None = Field(
        default=None,
        description="Optional override for OpenAI-compatible endpoints.",
    )

    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0)
    llm_system_prompt: str = Field(default=DEFAULT_SYSTEM_PROMPT, min_length=1)
    llm_temperature: float | None = Field(default=None, ge=0, le=2)
    llm_max_output_tokens: int | None = Field(default=None, gt=0)

    mock_chunk_delay_seconds: float = Field(
        default=0.0,
        ge=0,
        description="Pause before each streamed mock chunk, to watch or interrupt it.",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Minimum level for application logs (`app.*` loggers).",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
