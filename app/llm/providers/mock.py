from app.llm.types import LLMResult


class MockProvider:
    """Deterministic stand-in for a real model. Makes no network calls."""

    model_name = "mock-llm"

    async def generate(self, message: str) -> LLMResult:
        return LLMResult(text=f"Mock response to: {message}", model=self.model_name)

    async def aclose(self) -> None:
        pass
