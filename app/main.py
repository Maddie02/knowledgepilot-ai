from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.exception_handlers import register_exception_handlers
from app.logging_config import configure_logging
from app.routers.chat import router as chat_router
from app.routers.health import router as health_router
from app.services.llm import get_llm_service

configure_logging(get_settings().log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # Build the LLM service at startup so configuration problems are logged immediately.
    get_llm_service()
    yield
    # Close the provider's HTTP connection pool if one was created.
    if get_llm_service.cache_info().currsize:
        aclose = getattr(get_llm_service(), "aclose", None)
        if aclose is not None:
            await aclose()
        get_llm_service.cache_clear()


app = FastAPI(title="KnowledgePilot AI", lifespan=lifespan)

register_exception_handlers(app)
app.include_router(health_router)
app.include_router(chat_router)
