"""Composition root: builds the app and wires its resources (like @SpringBootApplication)."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.exception_handlers import register_exception_handlers
from app.api.routers.chat import router as chat_router
from app.api.routers.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.logging_setup import configure_logging
from app.llm import build_llm_provider


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
        app.state.llm_provider = build_llm_provider(resolved)
        try:
            yield
        finally:
            await app.state.llm_provider.aclose()

    app = FastAPI(title="KnowledgePilot AI", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(chat_router)
    return app


app = create_app()
