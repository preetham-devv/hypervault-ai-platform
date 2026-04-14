"""
OpenTelemetry tracing — TracerProvider with environment-aware exporters.

Production  (OTEL_EXPORTER_TYPE=gcp):     Cloud Trace exporter via
                                           opentelemetry-exporter-gcp-trace.
Development (OTEL_EXPORTER_TYPE=console): ConsoleSpanExporter to stdout.

Custom span helpers are provided for the three highest-value instrumentation
points in HyperVault:
  gemini_inference     — wraps Gemini / Vertex AI calls
  vector_search        — wraps pgvector similarity queries
  rls_context_switch   — wraps SET app.active_user round-trips

SQLAlchemy instrumentation is added automatically via
opentelemetry-instrumentation-sqlalchemy so every engine query emits a span.
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Generator
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
import sqlalchemy

logger = logging.getLogger(__name__)

_SERVICE_NAME = os.getenv("K_SERVICE", "hypervault-ai-platform")
_SERVICE_VERSION = os.getenv("K_REVISION", "local")

_tracer: trace.Tracer | None = None
_configured = False


def setup_tracing(engine: sqlalchemy.engine.Engine | None = None) -> None:
    """
    Configure the global OpenTelemetry TracerProvider.

    Safe to call multiple times — subsequent calls are no-ops. Pass an
    initialised SQLAlchemy *engine* to enable automatic query-level spans.

    Parameters
    ----------
    engine:
        The application's SQLAlchemy engine. When provided, the SQLAlchemy
        OTel instrumentation is applied so every ``execute()`` call emits a
        child span under the current trace context.
    """
    global _tracer, _configured
    if _configured:
        return

    resource = Resource.create({
        SERVICE_NAME: _SERVICE_NAME,
        SERVICE_VERSION: _SERVICE_VERSION,
    })

    provider = TracerProvider(resource=resource)

    exporter_type = os.getenv("OTEL_EXPORTER_TYPE", "console").lower()

    if exporter_type == "gcp":
        # Cloud Trace exporter — used on Cloud Run where GOOGLE_CLOUD_PROJECT
        # is set automatically.  Import is deferred so the package is not
        # required when running locally without the GCP SDK.
        try:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter  # type: ignore[import]
            gcp_exporter = CloudTraceSpanExporter()
            provider.add_span_processor(BatchSpanProcessor(gcp_exporter))
            logger.info("OTel: GCP Cloud Trace exporter configured")
        except ImportError:
            logger.warning(
                "OTEL_EXPORTER_TYPE=gcp but opentelemetry-exporter-gcp-trace "
                "is not installed — falling back to console exporter"
            )
            provider.add_span_processor(
                SimpleSpanProcessor(ConsoleSpanExporter())
            )
    else:
        # Console exporter for local development — prints span summaries to
        # stdout alongside structlog output.
        provider.add_span_processor(
            SimpleSpanProcessor(ConsoleSpanExporter())
        )
        logger.info("OTel: console span exporter configured")

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(__name__)

    # ── SQLAlchemy instrumentation ──────────────────────────────────────────
    if engine is not None:
        _instrument_sqlalchemy(engine)

    _configured = True


def _instrument_sqlalchemy(engine: sqlalchemy.engine.Engine) -> None:
    """Attach opentelemetry-instrumentation-sqlalchemy to *engine*."""
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor  # type: ignore[import]
        SQLAlchemyInstrumentor().instrument(engine=engine)
        logger.info("OTel: SQLAlchemy instrumentation enabled")
    except ImportError:
        logger.warning(
            "opentelemetry-instrumentation-sqlalchemy not installed — "
            "database query spans will not be emitted"
        )


def get_tracer() -> trace.Tracer:
    """
    Return the application's global tracer.

    If ``setup_tracing()`` was never called a no-op tracer is returned so
    callers do not need to guard against ``None``.
    """
    if _tracer is not None:
        return _tracer
    return trace.get_tracer(__name__)


# ── Custom span context managers ──────────────────────────────────────────────

@contextlib.contextmanager
def gemini_inference_span(
    model: str = "gemini-2.0-flash",
    prompt_preview: str = "",
    **attributes: Any,
) -> Generator[trace.Span, None, None]:
    """
    Context manager that wraps a Gemini / Vertex AI inference call in a span.

    Usage::

        with gemini_inference_span(model="gemini-2.0-flash",
                                   prompt_preview=prompt[:80]) as span:
            response = gemini_client.generate(prompt)
            span.set_attribute("response_length", len(response))

    Parameters
    ----------
    model:
        The Gemini model ID (recorded as ``gen_ai.request.model``).
    prompt_preview:
        A short excerpt of the prompt for debugging (first ~80 chars).
    **attributes:
        Any additional span attributes to set on entry.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span("gemini_inference") as span:
        span.set_attribute("gen_ai.system", "vertex_ai")
        span.set_attribute("gen_ai.request.model", model)
        if prompt_preview:
            span.set_attribute("gen_ai.prompt_preview", prompt_preview[:120])
        for key, value in attributes.items():
            span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(trace.StatusCode.ERROR, str(exc))
            raise


@contextlib.contextmanager
def vector_search_span(
    query_preview: str = "",
    top_k: int = 10,
    table: str = "",
    **attributes: Any,
) -> Generator[trace.Span, None, None]:
    """
    Context manager that wraps a pgvector similarity search in a span.

    Usage::

        with vector_search_span(query_preview=query[:60],
                                top_k=top_k, table="employees") as span:
            rows = conn.execute(sql, ...).fetchall()
            span.set_attribute("result_count", len(rows))

    Parameters
    ----------
    query_preview:
        Short excerpt of the search query string.
    top_k:
        The requested result limit (``LIMIT`` clause value).
    table:
        AlloyDB table being searched (``"employees"`` or
        ``"performance_reviews"``).
    **attributes:
        Any additional span attributes.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span("vector_search") as span:
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.operation", "cosine_similarity")
        if table:
            span.set_attribute("db.sql.table", table)
        span.set_attribute("vector_search.top_k", top_k)
        if query_preview:
            span.set_attribute("vector_search.query_preview", query_preview[:120])
        for key, value in attributes.items():
            span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(trace.StatusCode.ERROR, str(exc))
            raise


@contextlib.contextmanager
def rls_context_switch_span(
    username: str | None,
    operation: str = "set",
    **attributes: Any,
) -> Generator[trace.Span, None, None]:
    """
    Context manager that wraps a ``SET app.active_user`` round-trip in a span.

    Useful for measuring the overhead of RLS context switches and detecting
    abnormally slow ``SET`` executions that could indicate connection issues.

    Usage::

        with rls_context_switch_span(username=active_user, operation="set"):
            conn.execute(text("SET app.active_user = :u"), {"u": username})

    Parameters
    ----------
    username:
        The username being set (recorded as ``rls.username``).  ``None``
        means no user context (system-level query).
    operation:
        ``"set"`` or ``"clear"`` to distinguish the two switch directions.
    **attributes:
        Any additional span attributes.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span("rls_context_switch") as span:
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("rls.operation", operation)
        span.set_attribute("rls.username", username or "(none)")
        for key, value in attributes.items():
            span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(trace.StatusCode.ERROR, str(exc))
            raise
