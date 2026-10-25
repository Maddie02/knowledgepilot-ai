from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings, get_settings
from app.exception_handlers import register_exception_handlers
from app.logging_config import configure_logging
from app.routers.chat import router as chat_router
from app.routers.health import router as health_router
from app.services.llm import build_llm_service


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    `settings` defaults to the environment / `.env` (via `get_settings()`),
    resolved at startup. Tests pass explicit settings so they never depend on
    a developer's local `.env`.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        resolved = settings or get_settings()
        configure_logging(resolved.log_level)

        # The app owns its resources: created once at startup, closed at shutdown.
        app.state.settings = resolved
        app.state.llm_service = build_llm_service(resolved)
        try:
            yield
        finally:
            await app.state.llm_service.aclose()

    app = FastAPI(title="KnowledgePilot AI", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(chat_router)
    return app


app = create_app()
