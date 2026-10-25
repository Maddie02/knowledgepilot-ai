from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.dependencies import get_llm_service
from app.exception_handlers import BUSY, NOT_CONFIGURED, PROVIDER_ERROR, TIMED_OUT
from app.schemas.chat import ChatRequest, ChatResponse, ErrorResponse, TokenUsage
from app.services.llm import LLMService

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
    llm: Annotated[LLMService, Depends(get_llm_service)],
) -> ChatResponse:
    result = await llm.generate(request.message)
    usage = (
        TokenUsage(
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            total_tokens=result.usage.total_tokens,
        )
        if result.usage
        else None
    )
    return ChatResponse(reply=result.text, model=result.model, usage=usage)
