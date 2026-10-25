"""LLM integration: a provider-neutral interface and its implementations.

This module is the package's public API. Code outside `app.llm` should import
from here (`from app.llm import LLMProvider, LLMResult, LLMTimeoutError`), not
from the submodules, so the internal layout can change without breaking callers.

Modules inside the package import from the specific submodules instead (e.g.
`from app.llm.errors import ...`) to avoid circular imports.
"""

from app.llm.errors import (
    LLMConfigurationError,
    LLMError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.llm.factory import build_llm_provider
from app.llm.types import LLMProvider, LLMResult, LLMUsage

__all__ = [
    "LLMConfigurationError",
    "LLMError",
    "LLMProvider",
    "LLMProviderError",
    "LLMRateLimitError",
    "LLMResult",
    "LLMTimeoutError",
    "LLMUsage",
    "build_llm_provider",
]
