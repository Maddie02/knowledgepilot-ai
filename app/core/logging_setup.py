import logging

from app.core.request_context import request_id_var

APP_LOGGER = "app"
LOG_FORMAT = "%(levelname)-9s %(name)s [%(request_id)s] - %(message)s"


class RequestIdFilter(logging.Filter):
    """Add the current request ID to every record as `record.request_id`.

    Logs written outside a request (e.g. at startup) get `-`. A filter never
    drops records here; it only adds the attribute the format needs.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


def configure_logging(level: str) -> None:
    """Send `app.*` logs to stderr at the given level.

    Uvicorn only configures its own loggers, so without this our INFO logs
    (e.g. LLM latency and token usage) would be dropped. Only the `app`
    logger is configured, so third-party libraries keep their defaults.

    The filter sits on the handler, not the logger: logger filters only see
    records logged on that exact logger, while the handler sees all `app.*` records.
    """
    logger = logging.getLogger(APP_LOGGER)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        handler.addFilter(RequestIdFilter())
        logger.addHandler(handler)
    logger.setLevel(level)
