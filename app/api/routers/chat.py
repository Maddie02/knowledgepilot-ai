import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.api.dependencies import get_llm_provider
from app.api.exception_handlers import (
    BUSY,
    INTERNAL_ERROR,
    NOT_CONFIGURED,
    PROVIDER_ERROR,
    TIMED_OUT,
    llm_error_response,
)
from app.llm import (
    LLMError,
    LLMProvider,
    LLMProviderError,
    LLMStreamEnd,
    LLMTextDelta,
    LLMUsage,
)
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    StreamDelta,
    StreamDone,
    TokenUsage,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a message to the assistant",
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": (
                "Validation error: the body is malformed JSON, `message` is missing, "
                "not a string, empty or whitespace-only, too long, "
                "or the body contains unknown fields."
            ),
        },
        status.HTTP_502_BAD_GATEWAY: {
            "model": ErrorResponse,
            "description": f"The provider failed or returned an error (`{PROVIDER_ERROR}`).",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": (
                f"The provider is not configured or rejected the credentials/model "
                f"(`{NOT_CONFIGURED}`), or it is rate limiting (`{BUSY}`, may include "
                "a `Retry-After` header)."
            ),
        },
        status.HTTP_504_GATEWAY_TIMEOUT: {
            "model": ErrorResponse,
            "description": f"The provider did not respond in time (`{TIMED_OUT}`).",
        },
    },
)
async def chat(
    request: ChatRequest,
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> ChatResponse:
    result = await llm.generate(request.message)
    return ChatResponse(
        reply=result.text, model=result.model, usage=_token_usage(result.usage)
    )


@router.post(
    "/chat/stream",
    response_class=EventSourceResponse,
    summary="Send a message and stream the reply as Server-Sent Events",
    description=(
        "Streams `delta` events (`StreamDelta`) with pieces of the reply, then exactly "
        "one final event: `done` (`StreamDone`) on success or `error` "
        "(`ErrorResponse`) on failure. LLM failures are sent as an `error` event, "
        "not as an HTTP status. A stream that ends without `done` or `error` was "
        "cut off. See ADR-0005."
    ),
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Validation error: same rules as `POST /api/v1/chat`.",
        },
    },
)
async def chat_stream(
    request: ChatRequest,
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> AsyncIterator[ServerSentEvent]:
    received_text = False
    try:
        async for event in llm.stream(request.message):
            match event:
                case LLMTextDelta(text=text):
                    received_text = True
                    yield ServerSentEvent(event="delta", data=StreamDelta(text=text))

                case LLMStreamEnd(model=model, usage=usage):
                    if not received_text:
                        raise LLMProviderError("Provider returned an empty response")

                    yield ServerSentEvent(
                        event="done",
                        data=StreamDone(model=model, usage=_token_usage(usage)),
                    )

    except LLMError as exc:
        _, detail = llm_error_response(exc)
        logger.warning("LLM stream failed error=%s", type(exc).__name__)
        yield ServerSentEvent(event="error", data=ErrorResponse(detail=detail))

    except Exception:
        logger.exception("Unexpected error while streaming a chat reply")
        yield ServerSentEvent(event="error", data=ErrorResponse(detail=INTERNAL_ERROR))


def _token_usage(usage: LLMUsage | None) -> TokenUsage | None:
    if usage is None:
        return None

    return TokenUsage(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
    )
