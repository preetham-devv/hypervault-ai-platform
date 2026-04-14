"""
Sustainability router — ESG metrics and AI-powered carbon analysis.

Routes:
  GET  /api/v1/sustainability/metrics   — raw rows from sustainability_metrics
  POST /api/v1/sustainability/analyze   — Gemini ESG analysis of supplied metrics
"""

from __future__ import annotations

import structlog

from fastapi import APIRouter, HTTPException, status

from src.api.dependencies import CurrentUser, DBEngine
from src.api.schemas import (
    SustainabilityAnalyzeRequest,
    SustainabilityAnalyzeResponse,
    SustainabilityMetricsResponse,
)
from src.reasoning_engine.sustainability_analyzer import SustainabilityAnalyzer
from src.security.secure_query import SecureQueryExecutor

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/sustainability", tags=["Sustainability"])

# Sustainability data is organisation-wide — use the admin identity so RLS
# doesn't filter it per department. In a real app this would be a dedicated
# service account with a specific RLS policy.
_METRICS_USER = "eve"

_METRICS_SQL = "SELECT * FROM sustainability_metrics ORDER BY quarter, department;"


@router.get(
    "/metrics",
    response_model=SustainabilityMetricsResponse,
    summary="Raw ESG metrics",
    description=(
        "Returns all rows from the sustainability_metrics table, ordered by "
        "quarter and department. Always runs as the admin identity so no data "
        "is hidden by RLS (sustainability data is organisation-wide)."
    ),
)
def get_metrics(
    engine: DBEngine,
    user: CurrentUser,  # authenticated but not used for RLS on this table
) -> SustainabilityMetricsResponse:
    """Fetch all sustainability metrics — caller must be authenticated."""
    logger.info("get_metrics requested", user=user)
    try:
        rows = SecureQueryExecutor(engine).query(_METRICS_SQL, user=_METRICS_USER)
    except Exception as exc:
        logger.exception("get_metrics failed", user=user)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Database error: {exc}",
        ) from exc

    return SustainabilityMetricsResponse(metrics=rows, count=len(rows))


@router.post(
    "/analyze",
    response_model=SustainabilityAnalyzeResponse,
    summary="AI carbon footprint analysis",
    description=(
        "Send ESG metric rows to Gemini for analysis. Returns ranked department "
        "impact, reduction targets, quick wins vs. long-term strategies, and "
        "estimated cost savings. Typically called after GET /metrics."
    ),
)
def analyze_sustainability(
    body: SustainabilityAnalyzeRequest,
    user: CurrentUser,
) -> SustainabilityAnalyzeResponse:
    """
    Pass *body.metrics* to ``SustainabilityAnalyzer.analyze_carbon_footprint()``.

    The engine is not needed here — the analyzer calls Vertex AI directly,
    not AlloyDB. Data has already been fetched by GET /metrics.
    """
    logger.info("analyze_sustainability called", data_points=len(body.metrics), user=user)
    try:
        analysis = SustainabilityAnalyzer().analyze_carbon_footprint(body.metrics)
    except Exception as exc:
        logger.exception("analyze_sustainability failed", user=user)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gemini analysis error: {exc}",
        ) from exc

    return SustainabilityAnalyzeResponse(
        analysis=analysis,
        data_points=len(body.metrics),
    )
