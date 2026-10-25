"""Provider-neutral LLM errors.

Providers translate their SDK-specific exceptions into these, so the rest of
the app never depends on a particular SDK. Messages are for server-side
diagnostics only and are never returned to clients or logged by the API layer.
"""


class LLMError(Exception):
    """Base class for provider failures."""


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
