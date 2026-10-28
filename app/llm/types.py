"""Provider-neutral LLM contract: the interface and the values it returns."""

from collections.abc import AsyncGenerator
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


@dataclass(frozen=True)
class LLMTextDelta:
    """A piece of the reply, as soon as the provider produces it. Never empty."""

    text: str


@dataclass(frozen=True)
class LLMStreamEnd:
    """The last event of a successful stream."""

    model: str
    usage: LLMUsage | None = None


LLMStreamEvent = LLMTextDelta | LLMStreamEnd
"""One item of a provider stream: zero or more deltas, then exactly one end."""


class LLMProvider(Protocol):
    """Interface every language-model provider must implement.

    A `Protocol` is structural: any class with these methods qualifies, without
    declaring that it implements the interface (unlike a Java `implements`).
    """

    async def generate(self, message: str) -> LLMResult: ...

    def stream(self, message: str) -> AsyncGenerator[LLMStreamEvent]: ...

    async def aclose(self) -> None:
        """Release resources such as HTTP connection pools."""
        ...
