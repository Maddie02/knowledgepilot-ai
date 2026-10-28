import logging

import pytest

from app.core.logging_setup import APP_LOGGER, configure_logging
from app.core.request_context import request_id_var


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

    logging.getLogger("app.llm.providers.openai").info(
        "LLM request completed latency_ms=12"
    )

    assert (
        "INFO      app.llm.providers.openai [-] - LLM request completed latency_ms=12"
        in (capsys.readouterr().err)
    )


def test_level_filters_lower_messages(app_logger, capsys):
    configure_logging("WARNING")

    logging.getLogger("app.llm").info("hidden")
    logging.getLogger("app.llm").warning("shown")

    err = capsys.readouterr().err
    assert "hidden" not in err
    assert "shown" in err


def test_configure_logging_is_idempotent(app_logger):
    configure_logging("INFO")
    configure_logging("DEBUG")

    assert len(app_logger.handlers) == 1
    assert app_logger.level == logging.DEBUG


def test_logs_inside_a_request_carry_its_request_id(app_logger, capsys):
    configure_logging("INFO")

    token = request_id_var.set("req-123")
    try:
        logging.getLogger("app.api").info("inside")
    finally:
        request_id_var.reset(token)
    logging.getLogger("app.api").info("outside")

    err = capsys.readouterr().err
    assert "app.api [req-123] - inside" in err
    assert "app.api [-] - outside" in err
