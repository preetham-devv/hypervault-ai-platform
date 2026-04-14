"""
Reasoning router — Gemini-powered data analysis endpoints.

All endpoints execute SQL within the caller's RLS boundary, then forward
the filtered results to Gemini for natural-language reasoning.

Routes:
  POST /api/v1/reasoning/department-summary
  POST /api/v1/reasoning/employee-insights
  POST /api/v1/reasoning/custom
"""

from __future__ import annotations

import structlog

from fastapi import APIRouter, HTTPException, status

from src.api.dependencies import CurrentUser, DBEngine
from src.api.schemas import CustomAnalysisRequest, ReasoningResponse
from src.reasoning_engine.realtime_pipeline import RealtimePipeline

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/reasoning", tags=["Reasoning"])


def _pipeline(engine: DBEngine) -> RealtimePipeline:
    """Construct a RealtimePipeline from the injected engine."""
    return RealtimePipeline(engine)


@router.post(
    "/department-summary",
    response_model=ReasoningResponse,
    summary="Department performance summary",
    description=(
        "Aggregates headcount, average salary, and performance ratings per "
        "department, then asks Gemini to surface high/low performers and "
        "compensation gaps. Results are filtered by the caller's RLS context."
    ),
)
def department_summary(
    engine: DBEngine,
    user: CurrentUser,
) -> ReasoningResponse:
    """
    Run the pre-built department summary query and return Gemini's analysis.

    The active user's role determines which departments are visible:
      - admin  → all departments
      - manager → their own department only
      - employee → no department-level data (empty result)
    """
    try:
        result = _pipeline(engine).get_department_summary(active_user=user)
    except Exception as exc:
        logger.exception("department_summary failed", user=user)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Upstream error from AlloyDB/Gemini: {exc}",
        ) from exc

    return ReasoningResponse(**result)


@router.post(
    "/employee-insights",
    response_model=ReasoningResponse,
    summary="Employee performance insights",
    description=(
        "Fetches the 50 most recent performance reviews visible to the caller "
        "and asks Gemini to identify top performers, at-risk employees, and "
        "recurring feedback patterns."
    ),
)
def employee_insights(
    engine: DBEngine,
    user: CurrentUser,
) -> ReasoningResponse:
    """
    Return Gemini's analysis of recent performance reviews for the active user.
    """
    try:
        result = _pipeline(engine).get_employee_insights(active_user=user)
    except Exception as exc:
        logger.exception("employee_insights failed", user=user)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Upstream error from AlloyDB/Gemini: {exc}",
        ) from exc

    return ReasoningResponse(**result)


@router.post(
    "/custom",
    response_model=ReasoningResponse,
    summary="Custom SQL + AI analysis",
    description=(
        "Execute an arbitrary read-only SQL query under the caller's RLS "
        "context, then ask Gemini the provided question about the results. "
        "DDL and DML statements are rejected by schema validation."
    ),
)
def custom_analysis(
    body: CustomAnalysisRequest,
    engine: DBEngine,
    user: CurrentUser,
) -> ReasoningResponse:
    """
    Run ``body.sql`` as *user*, pass results to Gemini with ``body.question``.

    The ``CustomAnalysisRequest.no_ddl`` validator has already blocked DROP /
    TRUNCATE / etc. before we reach this handler. RLS still applies — even a
    SELECT * will only return rows the user is authorised to see.
    """
    try:
        result = _pipeline(engine).query_and_reason(
            sql=body.sql,
            question=body.question,
            active_user=user,
        )
    except Exception as exc:
        logger.exception("custom_analysis failed", user=user, sql_preview=body.sql[:80])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Upstream error from AlloyDB/Gemini: {exc}",
        ) from exc

    return ReasoningResponse(**result)
