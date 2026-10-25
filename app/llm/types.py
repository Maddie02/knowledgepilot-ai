"""Provider-neutral LLM contract: the interface and the values it returns."""

from dataclasses import dataclass
from typing import Protocol


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


class LLMProvider(Protocol):
    """Interface every language-model provider must implement.

    A `Protocol` is structural: any class with these methods qualifies, without
    declaring that it implements the interface (unlike a Java `implements`).
    """

    async def generate(self, message: str) -> LLMResult: ...

    async def aclose(self) -> None:
        """Release resources such as HTTP connection pools."""
        ...
