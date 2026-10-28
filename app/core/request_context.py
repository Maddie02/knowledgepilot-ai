"""Per-request values that code anywhere in the app can read without passing them around.

A `ContextVar` holds one value per asyncio task context. Every request runs in its
own context, so concurrent requests each see their own ID, and tasks started while
handling a request (such as FastAPI's SSE producer) inherit it.
"""

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
