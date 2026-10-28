import asyncio
import re
from collections.abc import AsyncGenerator

from app.llm.types import LLMResult, LLMStreamEnd, LLMStreamEvent, LLMTextDelta

# A word plus the whitespace after it: joining the chunks gives the text back exactly.
_CHUNK_PATTERN = re.compile(r"\S+\s*")


class MockProvider:
    """Deterministic stand-in for a real model. Makes no network calls."""

    model_name = "mock-llm"

    def __init__(self, chunk_delay: float = 0.0) -> None:
        """`chunk_delay` (seconds) slows the stream down so it can be watched."""
        self.chunk_delay = chunk_delay

    async def generate(self, message: str) -> LLMResult:
        return LLMResult(text=self._reply(message), model=self.model_name)

    async def stream(self, message: str) -> AsyncGenerator[LLMStreamEvent]:
        for chunk in _CHUNK_PATTERN.findall(self._reply(message)):
            # Always await: it lets other tasks run and is where cancellation arrives.
            await asyncio.sleep(self.chunk_delay)
            yield LLMTextDelta(text=chunk)
        yield LLMStreamEnd(model=self.model_name)

    async def aclose(self) -> None:
        pass

    @staticmethod
    def _reply(message: str) -> str:
        return f"Mock response to: {message}"
