"""
OpenTelemetry metrics — MeterProvider and application instruments.

Instruments registered here:
  query_duration_seconds        — histogram  — AlloyDB query wall-clock time
  rls_rows_filtered             — counter    — rows hidden by RLS policies
  vector_search_latency_ms      — histogram  — pgvector similarity search time
  gemini_inference_latency_ms   — histogram  — Gemini/Vertex AI round-trip time
  active_connections            — gauge      — current open SQLAlchemy connections

All instruments share the meter name ``hypervault`` to make filtering in
Cloud Monitoring dashboards straightforward.

Usage::

    from src.observability.metrics import (
        record_query_duration,
        record_rls_rows_filtered,
        record_vector_search_latency,
        record_gemini_inference_latency,
        set_active_connections,
    )
"""

from __future__ import annotations

import logging
import os
from typing import Any

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION

logger = logging.getLogger(__name__)

_SERVICE_NAME = os.getenv("K_SERVICE", "hypervault-ai-platform")
_SERVICE_VERSION = os.getenv("K_REVISION", "local")

_meter: metrics.Meter | None = None
_configured = False

# ── Instrument references (populated by setup_metrics) ────────────────────────
_query_duration: metrics.Histogram | None = None
_rls_rows_filtered: metrics.Counter | None = None
_vector_search_latency: metrics.Histogram | None = None
_gemini_inference_latency: metrics.Histogram | None = None
_active_connections: metrics.ObservableGauge | None = None

# Simple in-process counter used by the ObservableGauge callback.
# Incremented/decremented by set_active_connections().
_active_connections_value: int = 0


def setup_metrics() -> None:
    """
    Configure the global OpenTelemetry MeterProvider and register instruments.

    Safe to call multiple times — subsequent calls are no-ops.  Call once at
    application startup after ``configure_logging()`` and ``setup_tracing()``.
    """
    global _meter, _configured
    global _query_duration, _rls_rows_filtered
    global _vector_search_latency, _gemini_inference_latency
    global _active_connections

    if _configured:
        return

    resource = Resource.create({
        SERVICE_NAME: _SERVICE_NAME,
        SERVICE_VERSION: _SERVICE_VERSION,
    })

    exporter_type = os.getenv("OTEL_EXPORTER_TYPE", "console").lower()
    export_interval_ms = int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL_MS", "60000"))

    if exporter_type == "gcp":
        try:
            from opentelemetry.exporter.cloud_monitoring import (  # type: ignore[import]
                CloudMonitoringMetricsExporter,
            )
            exporter = CloudMonitoringMetricsExporter()
            logger.info("OTel metrics: GCP Cloud Monitoring exporter configured")
        except ImportError:
            logger.warning(
                "OTEL_EXPORTER_TYPE=gcp but opentelemetry-exporter-gcp-monitoring "
                "is not installed — falling back to console metric exporter"
            )
            exporter = ConsoleMetricExporter()
    else:
        exporter = ConsoleMetricExporter()
        logger.info("OTel metrics: console metric exporter configured")

    reader = PeriodicExportingMetricReader(
        exporter,
        export_interval_millis=export_interval_ms,
    )
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)

    _meter = metrics.get_meter("hypervault", version=_SERVICE_VERSION)

    # ── Register instruments ────────────────────────────────────────────────

    _query_duration = _meter.create_histogram(
        name="query_duration_seconds",
        description="Wall-clock time for AlloyDB query execution",
        unit="s",
    )

    _rls_rows_filtered = _meter.create_counter(
        name="rls_rows_filtered",
        description="Cumulative count of rows hidden by RLS policies",
        unit="rows",
    )

    _vector_search_latency = _meter.create_histogram(
        name="vector_search_latency_ms",
        description="Wall-clock time for pgvector cosine similarity searches",
        unit="ms",
    )

    _gemini_inference_latency = _meter.create_histogram(
        name="gemini_inference_latency_ms",
        description="Round-trip latency for Gemini / Vertex AI inference calls",
        unit="ms",
    )

    def _observe_active_connections(options: Any) -> list[metrics.Observation]:
        return [metrics.Observation(_active_connections_value)]

    _active_connections = _meter.create_observable_gauge(
        name="active_connections",
        callbacks=[_observe_active_connections],
        description="Current number of open SQLAlchemy connections",
        unit="connections",
    )

    _configured = True
    logger.info("OTel metrics: instruments registered")


# ── Public recording helpers ──────────────────────────────────────────────────

def record_query_duration(
    duration_s: float,
    *,
    table: str = "",
    operation: str = "",
    user: str = "",
) -> None:
    """
    Record the wall-clock time of an AlloyDB query.

    Parameters
    ----------
    duration_s:
        Elapsed seconds for the query (e.g. ``time.monotonic()`` delta).
    table:
        Primary table queried (label for filtering in dashboards).
    operation:
        SQL operation type: ``"select"``, ``"insert"``, etc.
    user:
        RLS username active during the query.
    """
    if _query_duration is None:
        return
    _query_duration.record(
        duration_s,
        attributes={"db.sql.table": table, "db.operation": operation, "rls.user": user},
    )


def record_rls_rows_filtered(count: int, *, table: str = "", user: str = "") -> None:
    """
    Increment the counter of rows hidden by RLS for the given *table* and *user*.

    Parameters
    ----------
    count:
        Number of rows that were filtered out by the RLS policy.
    table:
        Table the RLS policy was applied to.
    user:
        The ``app.active_user`` value at the time of filtering.
    """
    if _rls_rows_filtered is None or count <= 0:
        return
    _rls_rows_filtered.add(
        count,
        attributes={"db.sql.table": table, "rls.user": user},
    )


def record_vector_search_latency(
    duration_ms: float,
    *,
    table: str = "",
    top_k: int = 0,
    result_count: int = 0,
) -> None:
    """
    Record the latency of a pgvector similarity search.

    Parameters
    ----------
    duration_ms:
        Elapsed milliseconds for the search query.
    table:
        AlloyDB table searched (``"employees"`` or ``"performance_reviews"``).
    top_k:
        The requested ``LIMIT`` value.
    result_count:
        Actual number of rows returned (may be less than top_k if RLS filtered).
    """
    if _vector_search_latency is None:
        return
    _vector_search_latency.record(
        duration_ms,
        attributes={
            "db.sql.table": table,
            "vector_search.top_k": top_k,
            "vector_search.result_count": result_count,
        },
    )


def record_gemini_inference_latency(
    duration_ms: float,
    *,
    model: str = "gemini-2.0-flash",
    success: bool = True,
) -> None:
    """
    Record the round-trip latency of a Gemini inference call.

    Parameters
    ----------
    duration_ms:
        Elapsed milliseconds from sending the request to receiving the response.
    model:
        Gemini model ID used for the inference.
    success:
        ``False`` if the inference call raised an exception.
    """
    if _gemini_inference_latency is None:
        return
    _gemini_inference_latency.record(
        duration_ms,
        attributes={
            "gen_ai.request.model": model,
            "gen_ai.success": success,
        },
    )


def set_active_connections(count: int) -> None:
    """
    Update the gauge value for active SQLAlchemy connections.

    Call this from pool ``checkout`` (increment) and ``checkin`` (decrement)
    event listeners if you want real-time connection tracking.

    Parameters
    ----------
    count:
        The new absolute connection count.
    """
    global _active_connections_value
    _active_connections_value = max(0, count)
