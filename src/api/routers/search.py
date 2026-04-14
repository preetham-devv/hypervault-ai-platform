"""
Search router — vector similarity search endpoints.

Queries are embedded inline inside AlloyDB via ``google_ml.embedding()``;
no separate Python-to-Vertex round-trip is needed. Results respect the
caller's RLS context.

Routes:
  POST /api/v1/search/employees
  POST /api/v1/search/reviews
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from src.api.dependencies import CurrentUser, DBEngine
from src.api.schemas import SearchRequest, SearchResponse
from src.vector_engine.vector_search import VectorSearch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["Search"])


@router.post(
    "/employees",
    response_model=SearchResponse,
    summary="Semantic employee search",
    description=(
        "Find employees whose profile embedding is closest to the query string. "
        "Uses cosine similarity via AlloyDB's IVFFlat ANN index (sub-50ms). "
        "Results are filtered by the caller's RLS context."
    ),
)
def search_employees(
    body: SearchRequest,
    engine: DBEngine,
    user: CurrentUser,
) -> SearchResponse:
    """
    Embed *body.query* inside AlloyDB and return the *body.top_k* closest
    employee profiles, ordered by descending similarity score.
    """
    try:
        rows = VectorSearch(engine).search_employees(
            query=body.query,
            top_k=body.top_k,
            active_user=user,
        )
    except Exception as exc:
        logger.exception("search_employees failed query=%r user=%s", body.query[:60], user)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Vector search error: {exc}",
        ) from exc

    return SearchResponse(results=rows, count=len(rows))


@router.post(
    "/reviews",
    response_model=SearchResponse,
    summary="Semantic performance review search",
    description=(
        "Find performance reviews semantically closest to the query string. "
        "Joins back to the employees table to include the employee name. "
        "Results are filtered by the caller's RLS context."
    ),
)
def search_reviews(
    body: SearchRequest,
    engine: DBEngine,
    user: CurrentUser,
) -> SearchResponse:
    """
    Embed *body.query* inside AlloyDB and return the *body.top_k* closest
    performance review entries, ordered by descending similarity score.
    """
    try:
        rows = VectorSearch(engine).search_reviews(
            query=body.query,
            top_k=body.top_k,
            active_user=user,
        )
    except Exception as exc:
        logger.exception("search_reviews failed query=%r user=%s", body.query[:60], user)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Vector search error: {exc}",
        ) from exc

    return SearchResponse(results=rows, count=len(rows))
