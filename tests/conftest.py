import pytest

from app.main import app
from app.services.llm import MockLLMService, get_llm_service


@pytest.fixture(autouse=True)
def use_mock_llm():
    """Never call a real provider in tests, regardless of local `.env`."""
    app.dependency_overrides[get_llm_service] = MockLLMService
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def anyio_backend():
    return "asyncio"
