"""
Context Switcher — sets the PostgreSQL session variable that
drives Row-Level Security. Before every query we SET app.active_user
to the logged-in identity. RLS policies read this to filter rows.
"""

import sqlalchemy.exc
import structlog
from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.api.error_handlers import RLSViolationError

logger = structlog.get_logger(__name__)


def set_user_context(conn: Connection, username: str) -> None:
    """
    Brand the current PostgreSQL session with *username* for RLS enforcement.

    Sets the session variable ``app.active_user`` which is read by the RLS
    policies defined in ``rls_policies.sql``. Must be called at the start of
    every connection that should be subject to row-level filtering.

    Parameters
    ----------
    conn:
        An open SQLAlchemy connection (within a transaction).
    username:
        The authenticated user's identifier. Alphanumeric + underscores only
        — any other characters are stripped to prevent SET injection.

    Raises
    ------
    ValueError
        If *username* is blank, which would silently bypass RLS.
    RLSViolationError
        If the SET command fails due to a connection drop or timeout.
        The connection must be considered unusable after this exception.
    """
    if not username or not username.strip():
        # Refuse empty context — an unset variable could match overly-permissive
        # RLS policies and expose rows that should be hidden.
        raise ValueError("Empty user context — security violation")

    # Strip non-alphanumeric characters to neutralise SQL injection via the SET command.
    sanitized = "".join(c for c in username if c.isalnum() or c == "_")

    try:
        conn.execute(text("SET app.active_user = :u"), {"u": sanitized})
    except (sqlalchemy.exc.OperationalError, sqlalchemy.exc.InterfaceError) as exc:
        # Connection was dropped or timed out during the SET.
        # Raising RLSViolationError prevents the query from proceeding on a
        # connection whose RLS state is unknown — safer to abort than to risk
        # running without the correct user context.
        logger.error(
            "RLS context set failed — connection error",
            operation="set",
            error=str(exc),
            exc_type=type(exc).__name__,
        )
        raise RLSViolationError(
            f"Failed to set RLS context for user '{sanitized}': {exc}",
            username=sanitized,
            operation="set",
        ) from exc
    except sqlalchemy.exc.SQLAlchemyError as exc:
        logger.error(
            "RLS context set failed — unexpected SQL error",
            operation="set",
            error=str(exc),
        )
        raise RLSViolationError(
            f"Unexpected error setting RLS context for user '{sanitized}': {exc}",
            username=sanitized,
            operation="set",
        ) from exc

    logger.debug("RLS context set", active_user=sanitized)


def get_user_context(conn: Connection) -> str:
    """
    Read back the current ``app.active_user`` session variable.

    The second argument ``TRUE`` to ``current_setting`` suppresses the
    "unrecognized configuration parameter" error when the variable has not
    been set yet, returning NULL instead.

    Parameters
    ----------
    conn:
        An open SQLAlchemy connection.

    Returns
    -------
    str
        The current username, or an empty string if no context is set.
    """
    result = conn.execute(text("SELECT current_setting('app.active_user', TRUE)"))
    row = result.fetchone()
    return row[0] if row and row[0] else ""


def clear_user_context(conn: Connection) -> None:
    """
    Clear ``app.active_user`` by setting it to an empty string.

    Deliberately uses ``SET app.active_user = ''`` rather than
    ``RESET app.active_user`` because ``RESET`` raises
    "unrecognized configuration parameter" on connections where the variable
    was never set (e.g. system-level connections with no user context). The
    ``SET`` form is safe to call unconditionally.

    Parameters
    ----------
    conn:
        An open SQLAlchemy connection.

    Raises
    ------
    RLSViolationError
        If the SET command fails due to a connection drop or timeout.
        SecureConnection.__exit__ catches this, logs a WARNING, and still
        closes the connection — the pool's checkin listener provides the
        second-layer reset.
    """
    try:
        conn.execute(text("SET app.active_user = ''"))
    except (sqlalchemy.exc.OperationalError, sqlalchemy.exc.InterfaceError) as exc:
        logger.error(
            "RLS context clear failed — connection error",
            operation="clear",
            error=str(exc),
            exc_type=type(exc).__name__,
        )
        raise RLSViolationError(
            f"Failed to clear RLS context: {exc}",
            operation="clear",
        ) from exc
    except sqlalchemy.exc.SQLAlchemyError as exc:
        logger.error(
            "RLS context clear failed — unexpected SQL error",
            operation="clear",
            error=str(exc),
        )
        raise RLSViolationError(
            f"Unexpected error clearing RLS context: {exc}",
            operation="clear",
        ) from exc

    logger.debug("RLS context cleared")
