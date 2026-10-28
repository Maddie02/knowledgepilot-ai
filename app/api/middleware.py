"""Request ID and request latency for every HTTP request (see ADR-0006)."""

import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_context import request_id_var

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
# Only short, plain IDs are reused: anything else could forge log lines
# (newlines) or flood the logs (very long values).
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


class RequestContextMiddleware:
    """Pure ASGI middleware: no `BaseHTTPMiddleware`.

    `BaseHTTPMiddleware` wraps the response body in its own stream and runs the
    endpoint in a separate task, which complicates streaming responses. A plain
    ASGI middleware just wraps `send`, so a streamed body passes straight through,
    and its `finally` runs when the whole response is done, including the stream.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500  # if the app fails before sending a response

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            # `path` excludes the query string, which may contain sensitive data.
            logger.info(
                "HTTP request method=%s path=%s status=%s duration_ms=%.0f",
                scope["method"],
                scope["path"],
                status_code,
                (time.perf_counter() - started) * 1000,
            )
            request_id_var.reset(token)


def _incoming_request_id(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == b"x-request-id":
            candidate = value.decode("latin-1")
            return candidate if _VALID_REQUEST_ID.fullmatch(candidate) else None
    return None
