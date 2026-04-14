"""
SecureConnection — context manager that guarantees RLS context is always
cleared when a connection is released back to the pool.

The vulnerability it closes:
    SQLAlchemy pools reuse underlying pg8000 connections. PostgreSQL session
    variables (like ``app.active_user``) survive across connection.close()
    calls because "close" in pool mode just means "return to pool". Without
    an explicit RESET, the next caller that receives the same underlying
    connection would inherit the previous user's identity and see their rows.

Two-layer defence:
    1. SecureConnection.__exit__ explicitly resets app.active_user before
       handing the connection back to the pool (belt).
    2. The pool "checkin" event listener in config.py resets it again when
       the connection re-enters the pool (suspenders).
"""

from __future__ import annotations

import structlog
from types import TracebackType
from typing import Optional, Type

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from src.security.context_switcher import clear_user_context, set_user_context

logger = structlog.get_logger(__name__)


class SecureConnection:
    """
    Context manager that acquires a pooled connection, sets the PostgreSQL
    ``app.active_user`` session variable for RLS, and unconditionally clears
    it on exit — even if an exception is raised inside the ``with`` block.

    Usage::

        with SecureConnection(engine, "alice") as conn:
            rows = conn.execute(text("SELECT * FROM employees")).fetchall()
        # app.active_user has been reset; connection is back in the pool.

    Parameters
    ----------
    engine:
        SQLAlchemy engine connected to AlloyDB.
    username:
        The authenticated user identity. If ``None``, no context is set and
        the connection runs without an RLS boundary (system-level access).
        The clear step is still executed on exit for safety.
    """

    __slots__ = ("_engine", "_username", "_conn")

    def __init__(self, engine: Engine, username: Optional[str]) -> None:
        self._engine = engine
        self._username = username
        self._conn: Optional[Connection] = None

    def __enter__(self) -> Connection:
        """
        Acquire a connection from the pool and brand it with the user identity.

        Raises
        ------
        ValueError
            If ``username`` is a non-None blank string (propagated from
            ``set_user_context``). Blank strings are refused because an empty
            RLS context variable can silently match overly-permissive policies.
        """
        self._conn = self._engine.connect()
        if self._username:
            set_user_context(self._conn, self._username)
        return self._conn

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> bool:
        """
        Clear the user context and return the connection to the pool.

        The RESET always runs regardless of whether the body raised an
        exception. Errors during cleanup are logged and suppressed so they
        never mask the original exception from the caller.

        Returns
        -------
        bool
            Always ``False`` — exceptions from the ``with`` block are never
            suppressed here.
        """
        if self._conn is not None:
            try:
                # Always clear, even if username was None — the pool "checkin"
                # event does the same, but belt-and-suspenders matters here.
                clear_user_context(self._conn)
            except Exception:
                # Log at WARNING so it surfaces in monitoring without killing
                # the request or hiding the upstream exception (exc_type).
                logger.warning(
                    "Failed to clear RLS context — pool checkin event will attempt a second clear",
                    username=self._username,
                    exc_info=True,
                )
            finally:
                # close() returns the connection to the pool (does not destroy
                # the underlying pg8000 socket unless the pool is full).
                self._conn.close()
                self._conn = None

        return False  # Never suppress the caller's exception
