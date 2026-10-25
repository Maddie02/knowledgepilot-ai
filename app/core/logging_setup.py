import logging

APP_LOGGER = "app"
LOG_FORMAT = "%(levelname)-9s %(name)s - %(message)s"


def configure_logging(level: str) -> None:
    """Send `app.*` logs to stderr at the given level.

    Uvicorn only configures its own loggers, so without this our INFO logs
    (e.g. LLM latency and token usage) would be dropped. Only the `app`
    logger is configured, so third-party libraries keep their defaults.
    """
    logger = logging.getLogger(APP_LOGGER)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler)
    logger.setLevel(level)
