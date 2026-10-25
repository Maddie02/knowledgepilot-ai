from app.llm.errors import LLMConfigurationError
from app.llm.types import LLMResult


class UnconfiguredProvider:
    """Used when the selected provider is missing configuration.

    Lets the application start (so `/health` keeps working) while every chat
    request fails with a safe configuration error.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def generate(self, message: str) -> LLMResult:
        raise LLMConfigurationError(self.reason)

    async def aclose(self) -> None:
        pass
