"""
Error handlers — custom exceptions and FastAPI exception handlers.

Exception hierarchy:
    HyperVaultError                 (base)
    ├── DatabaseConnectionError     → 503 Service Unavailable
    ├── GeminiInferenceError        → 502 Bad Gateway
    ├── VectorSearchError           → 502 Bad Gateway
    └── RLSViolationError           → 500 Internal Server Error

Every JSON error response carries:
    error          — human-readable message
    error_code     — machine-readable SCREAMING_SNAKE_CASE identifier
    correlation_id — request UUID from structlog contextvars (X-Request-ID)
    detail         — optional structured context (model name, table, etc.)

Registration:
    Call ``register_error_handlers(app)`` once in ``src/api/main.py`` after
    the FastAPI application object is created.

Architectural note:
    The exception classes live here (in the API layer) so that the FastAPI
    handlers and the domain code share a single source of truth. Domain
    modules (vector_search, context_switcher, gemini_client) import directly
    from this module.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = structlog.get_logger(__name__)


# =============================================================================
# Custom exception classes
# =============================================================================

class HyperVaultError(Exception):
    """
    Base class for all HyperVault domain exceptions.

    Carries an optional ``context`` dict of structured key/value pairs that
    the exception handlers include in the JSON ``detail`` field for debugging.
    """

    #: Machine-readable error code returned in JSON responses. Subclasses
    #: override this.
    error_code: str = "HYPERVAULT_ERROR"

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        # Structured context forwarded to the error response detail field.
        self.context: dict[str, Any] = context


class DatabaseConnectionError(HyperVaultError):
    """
    Raised when the AlloyDB connection pool cannot acquire a live connection.

    Returned as HTTP 503 — the downstream database is unavailable, not the
    API itself, so callers should retry with backoff.

    Parameters
    ----------
    message:
        Human-readable description of the connection failure.
    host:
        AlloyDB instance IP or connection name (for diagnostics).
    db_name:
        Database name that could not be reached.
    """

    error_code = "DATABASE_CONNECTION_ERROR"

    def __init__(self, message: str, *, host: str = "", db_name: str = "", **context: Any) -> None:
        super().__init__(message, host=host, db_name=db_name, **context)


class GeminiInferenceError(HyperVaultError):
    """
    Raised when a Gemini / Vertex AI inference call fails.

    Returned as HTTP 502 — the upstream model API is unavailable or rejected
    the request. The ``retryable`` flag tells callers whether to retry.

    Parameters
    ----------
    message:
        Human-readable description of the inference failure.
    model:
        Gemini model ID that was called (e.g. ``"gemini-2.0-flash"``).
    retryable:
        ``True`` if the failure was transient (rate-limit, server error) and
        the caller may retry. ``False`` for permanent errors (bad request,
        permission denied).
    attempts:
        Number of attempts made before giving up (including the final failure).
    """

    error_code = "GEMINI_INFERENCE_ERROR"

    def __init__(
        self,
        message: str,
        *,
        model: str = "",
        retryable: bool = False,
        attempts: int = 1,
        **context: Any,
    ) -> None:
        super().__init__(message, model=model, retryable=retryable, attempts=attempts, **context)
        self.retryable = retryable
        self.model = model
        self.attempts = attempts


class VectorSearchError(HyperVaultError):
    """
    Raised when a pgvector similarity search fails.

    Returned as HTTP 502. The ``embeddings_missing`` flag is set when the
    failure is caused by missing pre-computed embeddings rather than a
    transient DB error, so callers can surface a more helpful message.

    Parameters
    ----------
    message:
        Human-readable description of the search failure.
    table:
        AlloyDB table that was being searched.
    query_preview:
        Short excerpt of the search query (first ~60 chars).
    embeddings_missing:
        ``True`` when the ``embedding`` column is NULL for all rows or the
        column does not yet exist — embeddings have not been generated.
    """

    error_code = "VECTOR_SEARCH_ERROR"

    def __init__(
        self,
        message: str,
        *,
        table: str = "",
        query_preview: str = "",
        embeddings_missing: bool = False,
        **context: Any,
    ) -> None:
        super().__init__(
            message,
            table=table,
            query_preview=query_preview,
            embeddings_missing=embeddings_missing,
            **context,
        )
        self.embeddings_missing = embeddings_missing


class RLSViolationError(HyperVaultError):
    """
    Raised when the RLS context switch (SET app.active_user) fails.

    Returned as HTTP 500 — this is a server-side security failure. A failed
    SET command means the query would either run with the wrong user identity
    or without any RLS filtering, so the connection is aborted rather than
    allowed to proceed.

    Parameters
    ----------
    message:
        Human-readable description of the RLS failure.
    username:
        The ``app.active_user`` value that could not be set.
    operation:
        ``"set"`` or ``"clear"`` depending on which direction failed.
    """

    error_code = "RLS_VIOLATION_ERROR"

    def __init__(
        self,
        message: str,
        *,
        username: str = "",
        operation: str = "",
        **context: Any,
    ) -> None:
        super().__init__(message, username=username, operation=operation, **context)
        self.username = username
        self.operation = operation


# =============================================================================
# Helper
# =============================================================================

def _correlation_id() -> str:
    """
    Return the request UUID bound by RequestIDMiddleware.

    Reads from structlog's contextvars so it works without passing the
    Request object through every layer of the call stack.
    """
    ctx = structlog.contextvars.get_contextvars()
    return ctx.get("request_id", "")


def _build_response(
    status_code: int,
    exc: HyperVaultError,
) -> JSONResponse:
    """Serialise a HyperVaultError into the standard error JSON shape."""
    body: dict[str, Any] = {
        "error": str(exc),
        "error_code": exc.error_code,
        "correlation_id": _correlation_id(),
    }
    if exc.context:
        body["detail"] = exc.context
    return JSONResponse(status_code=status_code, content=body)


# =============================================================================
# FastAPI exception handlers
# =============================================================================

async def handle_database_connection_error(
    request: Request,
    exc: DatabaseConnectionError,
) -> JSONResponse:
    """503 — AlloyDB pool could not obtain a live connection."""
    logger.error(
        "Database connection failed",
        path=request.url.path,
        host=exc.context.get("host"),
        db=exc.context.get("db_name"),
        error=str(exc),
        correlation_id=_correlation_id(),
    )
    return _build_response(503, exc)


async def handle_gemini_inference_error(
    request: Request,
    exc: GeminiInferenceError,
) -> JSONResponse:
    """502 — Gemini / Vertex AI call failed or exhausted retries."""
    logger.error(
        "Gemini inference error",
        path=request.url.path,
        model=exc.model,
        retryable=exc.retryable,
        attempts=exc.attempts,
        error=str(exc),
        correlation_id=_correlation_id(),
    )
    return _build_response(502, exc)


async def handle_vector_search_error(
    request: Request,
    exc: VectorSearchError,
) -> JSONResponse:
    """502 — pgvector similarity search failed."""
    logger.error(
        "Vector search error",
        path=request.url.path,
        table=exc.context.get("table"),
        embeddings_missing=exc.embeddings_missing,
        error=str(exc),
        correlation_id=_correlation_id(),
    )
    return _build_response(502, exc)


async def handle_rls_violation_error(
    request: Request,
    exc: RLSViolationError,
) -> JSONResponse:
    """500 — RLS context switch failed; request aborted to prevent data leakage."""
    # Log at CRITICAL — this is a security-relevant failure.
    logger.critical(
        "RLS context switch failed — request aborted",
        path=request.url.path,
        operation=exc.operation,
        # Never log the username at critical level in case it contains PII.
        username_set=bool(exc.username),
        error=str(exc),
        correlation_id=_correlation_id(),
    )
    return _build_response(500, exc)


async def handle_unhandled_exception(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    500 fallback for exceptions not covered by the specific handlers above.

    Deliberately omits the raw exception message from the response body to
    avoid leaking internal details to callers in production.
    """
    logger.exception(
        "Unhandled exception",
        path=request.url.path,
        exc_type=type(exc).__name__,
        correlation_id=_correlation_id(),
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "An unexpected internal error occurred.",
            "error_code": "INTERNAL_ERROR",
            "correlation_id": _correlation_id(),
        },
    )


# =============================================================================
# Registration
# =============================================================================

def register_error_handlers(app: FastAPI) -> None:
    """
    Register all custom exception handlers on *app*.

    Call this immediately after creating the FastAPI instance in
    ``src/api/main.py`` so the handlers are in place before any request
    can be processed.
    """
    app.add_exception_handler(DatabaseConnectionError, handle_database_connection_error)
    app.add_exception_handler(GeminiInferenceError, handle_gemini_inference_error)
    app.add_exception_handler(VectorSearchError, handle_vector_search_error)
    app.add_exception_handler(RLSViolationError, handle_rls_violation_error)
    # Catch-all for any Exception that slips through the endpoint handlers.
    app.add_exception_handler(Exception, handle_unhandled_exception)
