"""
Context Switcher — sets the PostgreSQL session variable that
drives Row-Level Security. Before every query we SET app.active_user
to the logged-in identity. RLS policies read this to filter rows.
"""

import logging
from sqlalchemy import text
from sqlalchemy.engine import Connection

logger = logging.getLogger(__name__)


def set_user_context(conn: Connection, username: str) -> None:
    if not username or not username.strip():
        raise ValueError("Empty user context — security violation")
    sanitized = "".join(c for c in username if c.isalnum() or c == "_")
    conn.execute(text("SET app.active_user = :u"), {"u": sanitized})
    logger.debug("RLS context → app.active_user = '%s'", sanitized)


def get_user_context(conn: Connection) -> str:
    result = conn.execute(text("SELECT current_setting('app.active_user', TRUE)"))
    row = result.fetchone()
    return row[0] if row and row[0] else ""


def clear_user_context(conn: Connection) -> None:
    conn.execute(text("RESET app.active_user"))
    logger.debug("RLS context cleared")
