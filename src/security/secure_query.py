"""
Secure Query — executes SQL within an RLS-enforced context.
The same SELECT * returns different rows depending on who is logged in.
"""

import logging
from typing import Any, Optional
import sqlalchemy
from sqlalchemy import text
from src.config import get_engine
from src.security.context_switcher import set_user_context

logger = logging.getLogger(__name__)


class SecureQueryExecutor:
    def __init__(self, engine: sqlalchemy.engine.Engine = None):
        self.engine = engine or get_engine()

    def query(self, sql: str, params: dict = None,
              user: str = None) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            if user:
                set_user_context(conn, user)
            result = conn.execute(text(sql), params or {})
            cols = list(result.keys())
            rows = [dict(zip(cols, r)) for r in result.fetchall()]
        logger.info("Secure query → %d rows (user=%s)", len(rows), user or "system")
        return rows

    def execute(self, sql: str, params: dict = None, user: str = None) -> int:
        with self.engine.connect() as conn:
            if user:
                set_user_context(conn, user)
            result = conn.execute(text(sql), params or {})
            conn.commit()
        return result.rowcount

    def compare_access(self, sql: str, users: list[str]) -> dict[str, list[dict]]:
        """Run same query as multiple users — demonstrates RLS in action."""
        results = {}
        for u in users:
            results[u] = self.query(sql, user=u)
            logger.info("User '%s' → %d rows", u, len(results[u]))
        return results
