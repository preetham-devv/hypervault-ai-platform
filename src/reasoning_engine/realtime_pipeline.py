"""
Real-time pipeline — AlloyDB data → Gemini → actionable insights.
Every query runs inside a user's RLS security boundary.
"""

from __future__ import annotations

from typing import Any, Optional

import sqlalchemy
import structlog
from sqlalchemy import text

from src.config import get_engine
from src.reasoning_engine.gemini_client import GeminiClient
from src.security.secure_connection import SecureConnection

logger = structlog.get_logger(__name__)


class RealtimePipeline:
    """
    Orchestrates the AlloyDB → Gemini reasoning loop.

    Each public method runs a SQL query under the caller's RLS context
    (so Gemini only ever sees rows the user is authorised to read), then
    forwards the result to Gemini for natural-language analysis.
    """

    def __init__(self, engine: Optional[sqlalchemy.engine.Engine] = None) -> None:
        """
        Parameters
        ----------
        engine:
            SQLAlchemy engine connected to AlloyDB. If omitted, one is
            created automatically from environment config.
        """
        self.engine = engine or get_engine()
        self.gemini = GeminiClient()

    def query_and_reason(
        self,
        sql: str,
        question: str,
        active_user: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Execute *sql* within the user's RLS boundary, then ask Gemini *question*.

        Parameters
        ----------
        sql:
            Raw SQL to execute against AlloyDB. RLS policies filter rows
            automatically based on the active user session variable.
        question:
            The analytical question passed to Gemini alongside the query results.
        active_user:
            Username to set as ``app.active_user`` session variable.
            If omitted the query runs without an RLS context (system-level access).

        Returns
        -------
        dict with keys:
            ``raw_data`` — list of row dicts returned by the query.
            ``row_count`` — number of visible rows (reflects RLS filtering).
            ``insight``   — Gemini's natural-language analysis.
            ``user_context`` — the effective username used for this query.
        """
        with SecureConnection(self.engine, active_user) as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchall()]

        data_context = self._format_data(columns, rows)
        logger.info("Sending rows to Gemini", row_count=len(rows), user=active_user or "system")
        insight = self.gemini.analyze_data(data_context, question)

        return {
            "raw_data": rows,
            "row_count": len(rows),
            "insight": insight,
            "user_context": active_user or "system",
        }

    def in_database_reasoning(self, prompt: str, active_user: Optional[str] = None) -> str:
        """
        Run Gemini inference entirely inside AlloyDB via ``google_ml.predict_row()``.

        Unlike ``query_and_reason()``, the model call never leaves the database —
        data is passed directly to Gemini within the same SQL transaction.
        This eliminates a Python ↔ Vertex AI network round-trip.

        Parameters
        ----------
        prompt:
            The instruction or question for Gemini.
        active_user:
            RLS context username. Applied before the predict call so the model
            only sees authorised rows if the prompt references table data.

        Returns
        -------
        str
            The raw text response from Gemini, or an empty string if no row
            was returned.
        """
        predict_sql = text("""
            SELECT google_ml.predict_row(
                model_id => 'gemini-2.0-flash',
                request_body => jsonb_build_object(
                    'contents', jsonb_build_array(
                        jsonb_build_object(
                            'role', 'user',
                            'parts', jsonb_build_array(
                                jsonb_build_object('text', :prompt)
                            )
                        )
                    )
                )
            ) AS response;
        """)
        with SecureConnection(self.engine, active_user) as conn:
            result = conn.execute(predict_sql, {"prompt": prompt})
            row = result.fetchone()
        return row[0] if row else ""

    def get_department_summary(self, active_user: Optional[str] = None) -> dict[str, Any]:
        """
        Aggregate department headcount, average salary, and performance rating,
        then ask Gemini to identify high/low performers and compensation gaps.

        Parameters
        ----------
        active_user:
            RLS context — managers see only their department; admins see all.

        Returns
        -------
        dict
            Same shape as ``query_and_reason()``.
        """
        sql = """
            SELECT e.department, COUNT(*) AS headcount,
                   ROUND(AVG(e.salary)::numeric, 2) AS avg_salary,
                   ROUND(AVG(pr.rating)::numeric, 2) AS avg_rating,
                   COUNT(CASE WHEN pr.rating >= 4 THEN 1 END) AS high_performers
            FROM employees e
            LEFT JOIN performance_reviews pr ON e.id = pr.employee_id
            GROUP BY e.department ORDER BY headcount DESC;
        """
        question = (
            "Analyze these department metrics. Which departments perform well? "
            "Which need attention? Any compensation vs performance mismatches?"
        )
        return self.query_and_reason(sql, question, active_user)

    def get_employee_insights(self, active_user: Optional[str] = None) -> dict[str, Any]:
        """
        Fetch the 50 most recent performance reviews and ask Gemini to surface
        top performers, at-risk employees, and recurring feedback patterns.

        Parameters
        ----------
        active_user:
            RLS context — employees see only their own record.

        Returns
        -------
        dict
            Same shape as ``query_and_reason()``.
        """
        sql = """
            SELECT e.name, e.department, e.salary, pr.rating,
                   pr.review_text, pr.review_date
            FROM employees e
            JOIN performance_reviews pr ON e.id = pr.employee_id
            ORDER BY pr.review_date DESC LIMIT 50;
        """
        question = (
            "Review these performance records. Identify top performers, "
            "employees needing support, and patterns in feedback."
        )
        return self.query_and_reason(sql, question, active_user)

    @staticmethod
    def _format_data(columns: list[str], rows: list[dict[str, Any]]) -> str:
        """
        Render query results as a pipe-delimited text table for Gemini's context.

        Caps at 100 rows to keep token usage bounded; appends a truncation
        notice when rows were dropped.

        Parameters
        ----------
        columns:
            Ordered list of column names.
        rows:
            List of row dicts from the database query.

        Returns
        -------
        str
            Human-readable table, or ``'No data returned.'`` for empty results.
        """
        if not rows:
            return "No data returned."
        header = " | ".join(columns)
        lines = [header, "-" * len(header)]
        for row in rows[:100]:
            lines.append(" | ".join(str(row.get(c, "")) for c in columns))
        if len(rows) > 100:
            lines.append(f"... and {len(rows) - 100} more rows")
        return "\n".join(lines)
