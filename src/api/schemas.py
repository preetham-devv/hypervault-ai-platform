"""
Pydantic schemas for all API request and response bodies.

Convention:
  - Request schemas end in  ...Request
  - Response schemas end in ...Response
  - Row-level data is typed as list[dict[str, Any]] to stay flexible as the
    AlloyDB schema evolves — tighter row models can be added per endpoint later.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Shared
# =============================================================================

class HealthResponse(BaseModel):
    status: str
    version: str


# =============================================================================
# Reasoning
# =============================================================================

class CustomAnalysisRequest(BaseModel):
    """Request body for POST /api/v1/reasoning/custom."""

    sql: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="SQL query to execute against AlloyDB (subject to caller's RLS).",
        examples=["SELECT name, department, salary FROM employees ORDER BY salary DESC;"],
    )
    question: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="Natural-language question passed to Gemini alongside the query results.",
        examples=["What patterns do you see in compensation across departments?"],
    )

    @field_validator("sql")
    @classmethod
    def no_ddl(cls, v: str) -> str:
        """Reject DDL statements — this endpoint is read-only."""
        first_word = v.strip().split()[0].upper()
        if first_word in {"DROP", "TRUNCATE", "ALTER", "CREATE", "DELETE", "UPDATE", "INSERT"}:
            raise ValueError(f"DDL/DML not allowed via this endpoint: {first_word}")
        return v


class ReasoningResponse(BaseModel):
    """Unified response for all reasoning endpoints."""

    raw_data: list[dict[str, Any]] = Field(description="Rows returned by the SQL query.")
    row_count: int = Field(description="Number of rows visible after RLS filtering.")
    insight: str = Field(description="Gemini's natural-language analysis.")
    user_context: str = Field(description="Username whose RLS context was applied.")


# =============================================================================
# Search
# =============================================================================

class SearchRequest(BaseModel):
    """Request body for POST /api/v1/search/employees and /reviews."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="Free-text search string embedded by AlloyDB google_ml.embedding().",
        examples=["senior engineer cloud infrastructure"],
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of nearest-neighbour results to return.",
    )


class SearchResponse(BaseModel):
    """Response for vector similarity search endpoints."""

    results: list[dict[str, Any]] = Field(
        description="Matching rows ordered by descending similarity score."
    )
    count: int = Field(description="Number of results returned.")


# =============================================================================
# Security / RLS demo
# =============================================================================

class SecurityCompareResponse(BaseModel):
    """
    Response for GET /api/v1/security/compare-access.

    Maps each demo username to the rows that user can see when the same SQL
    query is executed under their RLS context.
    """

    sql: str = Field(description="The SQL that was executed for all users.")
    comparison: dict[str, list[dict[str, Any]]] = Field(
        description="Per-user row visibility map: {username: [rows]}."
    )


class SecurityMyViewResponse(BaseModel):
    """Response for GET /api/v1/security/my-view."""

    rows: list[dict[str, Any]]
    row_count: int
    user: str


# =============================================================================
# Sustainability / ESG
# =============================================================================

class SustainabilityMetricsResponse(BaseModel):
    """Response for GET /api/v1/sustainability/metrics."""

    metrics: list[dict[str, Any]] = Field(
        description="Raw rows from the sustainability_metrics table."
    )
    count: int


class SustainabilityAnalyzeRequest(BaseModel):
    """
    Request body for POST /api/v1/sustainability/analyze.

    Accepts the metrics rows directly so the client controls which data
    is sent for analysis (e.g. a filtered subset).
    """

    metrics: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        description="Sustainability metric rows to analyse.",
    )


class SustainabilityAnalyzeResponse(BaseModel):
    """Response for POST /api/v1/sustainability/analyze."""

    analysis: str = Field(description="Gemini's ESG analysis and recommendations.")
    data_points: int = Field(description="Number of metric rows analysed.")
