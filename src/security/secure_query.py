"""
Secure Query — executes SQL within an RLS-enforced context.
The same SELECT * returns different rows depending on who is logged in.
"""

from __future__ import annotations

from typing import Any, Optional

import sqlalchemy
import structlog
from sqlalchemy import text

from src.config import get_engine
from src.security.secure_connection import SecureConnection

logger = structlog.get_logger(__name__)


class SecureQueryExecutor:
    """
    Executes SQL under a user's RLS security context.

    Every method sets ``app.active_user`` on the connection before running
    SQL, ensuring AlloyDB's row-level security policies automatically filter
    results to only the rows that user is authorised to see.
    """

    def __init__(self, engine: Optional[sqlalchemy.engine.Engine] = None) -> None:
        """
        Parameters
        ----------
        engine:
            SQLAlchemy engine connected to AlloyDB. Created from environment
            config if not provided.
        """
        self.engine = engine or get_engine()

    def query(
        self,
        sql: str,
        params: Optional[dict[str, Any]] = None,
        user: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Run a SELECT query and return results filtered by RLS for *user*.

        Parameters
        ----------
        sql:
            The SQL query to execute. RLS policies silently filter rows —
            the same SQL returns different results for different users.
        params:
            Optional bind parameters for the query (prevents SQL injection).
        user:
            Username to set as the RLS context. If omitted, the query runs
            without a user context (system-level access, no RLS filtering).

        Returns
        -------
        list[dict]
            List of row dicts with column names as keys.
        """
        with SecureConnection(self.engine, user) as conn:
            result = conn.execute(text(sql), params or {})
            cols = list(result.keys())
            rows = [dict(zip(cols, r)) for r in result.fetchall()]
        logger.info("Secure query complete", row_count=len(rows), user=user or "system")
        return rows

    def execute(
        self,
        sql: str,
        params: Optional[dict[str, Any]] = None,
        user: Optional[str] = None,
    ) -> int:
        """
        Run a DML statement (INSERT / UPDATE / DELETE) within an RLS context.

        The transaction is committed automatically on success. RLS policies
        apply to the affected rows just as they do for SELECT queries.

        Parameters
        ----------
        sql:
            DML SQL statement to execute.
        params:
            Optional bind parameters.
        user:
            Username to set as the RLS context before execution.

        Returns
        -------
        int
            Number of rows affected by the statement.
        """
        with SecureConnection(self.engine, user) as conn:
            result = conn.execute(text(sql), params or {})
            conn.commit()
        return result.rowcount

    def compare_access(self, sql: str, users: list[str]) -> dict[str, list[dict[str, Any]]]:
        """
        Run the same SQL as each user and return a per-user result map.

        Demonstrates RLS in action: identical SQL, different visible rows.
        Used by the Security Demo tab in the Streamlit dashboard.

        Parameters
        ----------
        sql:
            The query to execute for every user.
        users:
            List of usernames to impersonate in turn.

        Returns
        -------
        dict[str, list[dict]]
            Maps each username to the rows visible to that user.
        """
        results = {}
        for u in users:
            results[u] = self.query(sql, user=u)
            logger.info("User row count", user=u, row_count=len(results[u]))
        return results
