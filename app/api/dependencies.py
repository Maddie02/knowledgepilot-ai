"""FastAPI dependencies that expose application-owned resources to routes."""

from fastapi import Request

from app.llm import LLMProvider


def get_llm_provider(request: Request) -> LLMProvider:
    """Return the LLM provider created by the app's lifespan.

    The provider is owned by the application instance (see `app.main.lifespan`)
    rather than a module-level cache, so every app - including each test app -
    gets its own provider, and shutdown closes it. Tests can still replace it
    with `app.dependency_overrides[get_llm_provider]`.
    """
    provider: LLMProvider = request.app.state.llm_provider
    return provider
