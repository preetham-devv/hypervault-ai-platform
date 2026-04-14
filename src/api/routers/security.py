"""
Security router — Zero Trust RLS demonstration endpoints.

These endpoints run the same SQL query under different user identities to
show how AlloyDB RLS silently filters rows based on app.active_user.

Routes:
  GET /api/v1/security/compare-access   — run as ALL demo users, compare results
  GET /api/v1/security/my-view          — run as the caller only
"""

from __future__ import annotations

import structlog

from fastapi import APIRouter, HTTPException, Query, status

from src.api.dependencies import CurrentUser, DBEngine, VALID_USERS
from src.api.schemas import SecurityCompareResponse, SecurityMyViewResponse
from src.security.secure_query import SecureQueryExecutor

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/security", tags=["Security"])

# The canonical demo query — identical SQL, different rows per user.
_DEMO_SQL = "SELECT id, name, department, role, salary FROM employees ORDER BY id;"


@router.get(
    "/compare-access",
    response_model=SecurityCompareResponse,
    summary="Compare row visibility across all users",
    description=(
        "Runs the same SELECT against AlloyDB once per demo user and returns "
        "a map of {username → visible rows}. Demonstrates how RLS enforces "
        "zero-trust data access at the database layer — no app-level filtering."
    ),
)
def compare_access(
    engine: DBEngine,
    user: CurrentUser,  # caller must be authenticated to trigger this demo
    sql: str = Query(
        default=_DEMO_SQL,
        max_length=2048,
        description="Override the demo SQL (read-only; DDL is not validated here).",
    ),
) -> SecurityCompareResponse:
    """
    Execute *sql* as every known demo user and collect the results.

    The caller's identity is validated by the dependency but not used to filter
    the comparison — the whole point is to show ALL users' views side-by-side.
    Each user's query runs in its own connection so RLS contexts don't bleed.
    """
    logger.info("compare_access triggered", user=user)
    try:
        executor = SecureQueryExecutor(engine)
        comparison = executor.compare_access(sql, list(VALID_USERS))
    except Exception as exc:
        logger.exception("compare_access failed", user=user)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"RLS comparison error: {exc}",
        ) from exc

    return SecurityCompareResponse(sql=sql, comparison=comparison)


@router.get(
    "/my-view",
    response_model=SecurityMyViewResponse,
    summary="Show rows visible to the current user",
    description=(
        "Runs the demo SELECT under the caller's RLS context and returns only "
        "the rows they are authorised to see."
    ),
)
def my_view(
    engine: DBEngine,
    user: CurrentUser,
    sql: str = Query(
        default=_DEMO_SQL,
        max_length=2048,
        description="Override the demo SQL.",
    ),
) -> SecurityMyViewResponse:
    """Return the rows visible to the calling user for the given *sql*."""
    try:
        rows = SecureQueryExecutor(engine).query(sql, user=user)
    except Exception as exc:
        logger.exception("my_view failed", user=user)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Query error: {exc}",
        ) from exc

    return SecurityMyViewResponse(rows=rows, row_count=len(rows), user=user)
