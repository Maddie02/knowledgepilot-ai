from typing import Protocol


class LLMService(Protocol):
    """Interface every language-model provider must implement."""

    model_name: str

    def generate(self, message: str) -> str: ...


class MockLLMService:
    """Deterministic stand-in for a real model. Makes no network calls."""

    model_name = "mock-llm"

    def generate(self, message: str) -> str:
        return f"Mock response to: {message}"


def get_llm_service() -> LLMService:
    """FastAPI dependency that provides the active LLM service."""
    return MockLLMService()
