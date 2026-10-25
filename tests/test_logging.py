import logging

import pytest

from app.config import Settings
from app.logging_config import APP_LOGGER, configure_logging


@pytest.fixture
def app_logger():
    logger = logging.getLogger(APP_LOGGER)
    handlers, level = list(logger.handlers), logger.level
    logger.handlers.clear()
    yield logger
    logger.handlers[:] = handlers
    logger.setLevel(level)


def test_info_logs_are_emitted(app_logger, capsys):
    configure_logging("INFO")

    logging.getLogger("app.services.openai_llm").info("LLM request completed latency_ms=12")

    assert "INFO      app.services.openai_llm - LLM request completed latency_ms=12" in (
        capsys.readouterr().err
    )


def test_level_filters_lower_messages(app_logger, capsys):
    configure_logging("WARNING")

    logging.getLogger("app.services").info("hidden")
    logging.getLogger("app.services").warning("shown")

    err = capsys.readouterr().err
    assert "hidden" not in err
    assert "shown" in err


def test_configure_logging_is_idempotent(app_logger):
    configure_logging("INFO")
    configure_logging("DEBUG")

    assert len(app_logger.handlers) == 1
    assert app_logger.level == logging.DEBUG


def test_log_level_defaults_to_info_and_validates(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    assert Settings(_env_file=None).log_level == "INFO"
    with pytest.raises(ValueError):
        Settings(_env_file=None, log_level="LOUD")
