import pytest

from app.llm import LLMConfigurationError, LLMStreamEnd
from app.llm.providers.mock import MockProvider
from app.llm.providers.unconfigured import UnconfiguredProvider
from tests.llm.stream_utils import collect_stream

pytestmark = pytest.mark.anyio


async def test_mock_stream_joins_to_the_generate_reply():
    provider = MockProvider()
    message = "Hello  big\nworld"  # double space and newline: whitespace must survive

    texts, end = await collect_stream(provider.stream(message))

    assert "".join(texts) == (await provider.generate(message)).text
    assert len(texts) > 1  # it really is split into several deltas
    assert end == LLMStreamEnd(model="mock-llm", usage=None)


async def test_unconfigured_stream_raises_on_first_read_not_on_call():
    stream = UnconfiguredProvider("missing key").stream("Hi")  # must not raise

    with pytest.raises(LLMConfigurationError):
        await anext(stream)
