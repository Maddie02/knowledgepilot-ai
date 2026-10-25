from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_MESSAGE_LENGTH = 4000

ChatMessage = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_LENGTH),
]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: ChatMessage = Field(
        description=(
            "The user's message. Leading and trailing whitespace is removed; "
            f"the result must be between 1 and {MAX_MESSAGE_LENGTH} characters."
        ),
        examples=["What is our vacation policy?"],
    )


class ChatResponse(BaseModel):
    reply: str = Field(
        description="The assistant's reply.",
        examples=["Mock response to: What is our vacation policy?"],
    )
    model: str = Field(
        description="Identifier of the model that produced the reply.",
        examples=["mock-llm"],
    )
