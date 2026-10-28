from collections.abc import AsyncIterator

from app.llm import LLMStreamEnd, LLMStreamEvent, LLMTextDelta


async def collect_stream(
    stream: AsyncIterator[LLMStreamEvent],
) -> tuple[list[str], LLMStreamEnd]:
    """Read a whole provider stream and check its shape.

    Returns the delta texts and the end event. Fails if the stream is not
    zero or more non-empty deltas followed by exactly one end event.
    """
    *deltas, end = [event async for event in stream]
    assert isinstance(end, LLMStreamEnd)
    texts = []
    for delta in deltas:
        assert isinstance(delta, LLMTextDelta)
        assert delta.text
        texts.append(delta.text)
    return texts, end
