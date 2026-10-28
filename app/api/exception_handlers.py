import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.llm import (
    LLMConfigurationError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)

NOT_CONFIGURED = "LLM provider is not configured"
TIMED_OUT = "LLM provider timed out"
BUSY = "LLM provider is busy, try again later"
PROVIDER_ERROR = "LLM provider error"
INTERNAL_ERROR = "Internal server error"


def llm_error_response(exc: LLMError) -> tuple[int, str]:
    """Map an LLM error to an HTTP status and a safe message for clients."""

    if isinstance(exc, LLMConfigurationError):
        return status.HTTP_503_SERVICE_UNAVAILABLE, NOT_CONFIGURED

    if isinstance(exc, LLMTimeoutError):
        return status.HTTP_504_GATEWAY_TIMEOUT, TIMED_OUT

    if isinstance(exc, LLMRateLimitError):
        return status.HTTP_503_SERVICE_UNAVAILABLE, BUSY

    return status.HTTP_502_BAD_GATEWAY, PROVIDER_ERROR


async def llm_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Starlette types handlers as taking any Exception; this one is only
    # registered for LLMError (see register_exception_handlers).
    if not isinstance(exc, LLMError):
        raise exc

    status_code, detail = llm_error_response(exc)
    # Fixed fields only: never log the exception message (it is free text).
    logger.warning(
        "LLM request failed method=%s path=%s error=%s status_code=%s",
        request.method,
        request.url.path,
        type(exc).__name__,
        status_code,
    )

    headers: dict[str, str] = {}
    if isinstance(exc, LLMRateLimitError) and exc.retry_after:
        headers["Retry-After"] = exc.retry_after
    return JSONResponse(
        status_code=status_code, content={"detail": detail}, headers=headers
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(LLMError, llm_error_handler)
