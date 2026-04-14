"""
Real-time pipeline — AlloyDB data → Gemini → actionable insights.
Every query runs inside a user's RLS security boundary.
"""

import logging
from typing import Any, Optional
import sqlalchemy
from sqlalchemy import text
from src.config import get_engine
from src.reasoning_engine.gemini_client import GeminiClient
from src.security.context_switcher import set_user_context

logger = logging.getLogger(__name__)


class RealtimePipeline:
    def __init__(self, engine: sqlalchemy.engine.Engine = None):
        self.engine = engine or get_engine()
        self.gemini = GeminiClient()

    def query_and_reason(self, sql: str, question: str,
                         active_user: str = None) -> dict[str, Any]:
        with self.engine.connect() as conn:
            if active_user:
                set_user_context(conn, active_user)
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchall()]

        data_context = self._format_data(columns, rows)
        logger.info("Sending %d rows to Gemini (user=%s)", len(rows), active_user or "system")
        insight = self.gemini.analyze_data(data_context, question)

        return {
            "raw_data": rows,
            "row_count": len(rows),
            "insight": insight,
            "user_context": active_user or "system",
        }

    def in_database_reasoning(self, prompt: str, active_user: str = None) -> str:
        """Run Gemini inference entirely inside AlloyDB. Data never leaves the DB."""
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
        with self.engine.connect() as conn:
            if active_user:
                set_user_context(conn, active_user)
            result = conn.execute(predict_sql, {"prompt": prompt})
            row = result.fetchone()
        return row[0] if row else ""

    def get_department_summary(self, active_user: str = None) -> dict:
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

    def get_employee_insights(self, active_user: str = None) -> dict:
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
    def _format_data(columns: list[str], rows: list[dict]) -> str:
        if not rows:
            return "No data returned."
        header = " | ".join(columns)
        lines = [header, "-" * len(header)]
        for row in rows[:100]:
            lines.append(" | ".join(str(row.get(c, "")) for c in columns))
        if len(rows) > 100:
            lines.append(f"... and {len(rows) - 100} more rows")
        return "\n".join(lines)
