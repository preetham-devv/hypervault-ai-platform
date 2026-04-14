"""
Logging configuration — structlog with environment-aware rendering.

Production  (APP_ENV=production):  JSON output that Cloud Logging parses as
                                   structured log entries and indexes by field.
Development (APP_ENV=development): Colored, human-readable ConsoleRenderer.

Every log event automatically carries these fields via shared processors:
  request_id  — UUID injected by RequestIDMiddleware, propagated via contextvars
  user        — caller identity bound by FastAPI endpoints via bind_request_context()
  timestamp   — ISO-8601 UTC
  level       — log level string (info, warning, error …)
  module      — Python module name (__name__ of the logger)
  func_name   — calling function name
  lineno      — source line number

Stdlib bridge:
  All third-party libraries that use stdlib logging (SQLAlchemy, httpx, uvicorn …)
  are routed through structlog's ProcessorFormatter so their output is also
  structured JSON in production.
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ── Shared processors ─────────────────────────────────────────────────────────
# These run on every log event regardless of renderer (JSON or console).
_SHARED_PROCESSORS: list[Any] = [
    # Pull bound context vars (request_id, user) into every log event.
    structlog.contextvars.merge_contextvars,
    # Add stdlib log level string ("info", "warning", …).
    structlog.stdlib.add_log_level,
    # Add the logger name (__name__ of the module calling get_logger()).
    structlog.stdlib.add_logger_name,
    # Render %-style positional format strings before structlog sees them.
    # Allows legacy code using logger.info("msg %s", arg) to keep working.
    structlog.stdlib.PositionalArgumentsFormatter(),
    # ISO-8601 UTC timestamp on every event.
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    # Add module, function, and line number from the call site.
    structlog.processors.CallsiteParameterAdder([
        structlog.processors.CallsiteParameter.MODULE,
        structlog.processors.CallsiteParameter.FUNC_NAME,
        structlog.processors.CallsiteParameter.LINENO,
    ]),
    # Render stack info and format exception tracebacks inline.
    structlog.processors.StackInfoRenderer(),
    structlog.processors.ExceptionRenderer(),
]

_configured = False


def configure_logging(force: bool = False) -> None:
    """
    Configure structlog and the stdlib logging bridge.

    Safe to call multiple times — subsequent calls are no-ops unless
    ``force=True``. Call once at application startup (before any logger
    is used) to ensure consistent output format.

    Parameters
    ----------
    force:
        If ``True``, reconfigure even if already configured. Useful in tests.
    """
    global _configured
    if _configured and not force:
        return

    app_env = os.getenv("APP_ENV", "development").lower()
    log_level_str = os.getenv("LOG_LEVEL", "DEBUG" if app_env == "development" else "INFO")
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)

    is_production = app_env == "production"

    # ── Final renderer ──────────────────────────────────────────────────────
    if is_production:
        # JSON: one compact log entry per line, ready for Cloud Logging.
        final_renderer = structlog.processors.JSONRenderer()
    else:
        # Colored, human-readable output for local development.
        final_renderer = structlog.dev.ConsoleRenderer(colors=True)

    # ── Configure structlog ─────────────────────────────────────────────────
    # IMPORTANT: remove_processors_meta must NOT appear here.
    # It deletes the '_record' key that the stdlib bridge injects into event
    # dicts. Native structlog events never have '_record', so adding it here
    # would raise KeyError on every native log call. It belongs exclusively in
    # the ProcessorFormatter.processors list below (stdlib bridge only).
    structlog.configure(
        processors=_SHARED_PROCESSORS + [final_renderer],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        cache_logger_on_first_use=True,
    )

    # ── Stdlib bridge ────────────────────────────────────────────────────────
    # Route all stdlib loggers (SQLAlchemy, uvicorn, httpx, google-cloud …)
    # through structlog's ProcessorFormatter so their output is also JSON
    # in production.
    formatter = structlog.stdlib.ProcessorFormatter(
        # Pre-chain runs only on records that arrive from stdlib logging.
        foreign_pre_chain=_SHARED_PROCESSORS,
        # Processors run on both native structlog events and stdlib events.
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            final_renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Remove any existing handlers (e.g. uvicorn's default stderr handler)
    # to avoid duplicate output.
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    # Silence noisy third-party loggers that produce unhelpful INFO-level spam.
    for noisy in (
        "google.auth",
        "google.api_core.bidi",
        "urllib3.connectionpool",
        "httpcore",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


# ── Request ID middleware ─────────────────────────────────────────────────────

class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that assigns a UUID to every HTTP request and binds
    it to structlog's contextvars so every log line in that request carries
    ``request_id``.

    The request ID is also echoed in the ``X-Request-ID`` response header so
    callers can correlate client-side errors with backend log entries.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # Honour a forwarded request ID from a load balancer or the caller,
        # or generate a fresh UUID.
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Clear any stale context from a previous request on this thread/task,
        # then bind the new values for the lifetime of this request.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def bind_request_context(user: str) -> None:
    """
    Bind the authenticated user to structlog's contextvars for the current
    request. Call this inside a FastAPI endpoint or dependency after the user
    identity has been validated.

    Parameters
    ----------
    user:
        The validated username (from X-User-Identity header).
    """
    structlog.contextvars.bind_contextvars(user=user)
