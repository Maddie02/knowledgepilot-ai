from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.llm import LLMService, get_llm_service

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
    },
)
def chat(
    request: ChatRequest,
    llm: Annotated[LLMService, Depends(get_llm_service)],
) -> ChatResponse:
    reply = llm.generate(request.message)
    return ChatResponse(reply=reply, model=llm.model_name)
