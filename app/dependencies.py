"""FastAPI dependencies that expose application-owned resources to routes."""

from fastapi import Request

from app.services.llm import LLMService


def get_llm_service(request: Request) -> LLMService:
    """Return the LLM service created by the app's lifespan.

    The service is owned by the application instance (see `app.main.lifespan`)
    rather than a module-level cache, so every app - including each test app -
    gets its own service, and shutdown closes it. Tests can still replace it
    with `app.dependency_overrides[get_llm_service]`.
    """
    return request.app.state.llm_service
