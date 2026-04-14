"""
Tests for RLS connection pooling safety.

Verifies that:
  1. SecureConnection sets app.active_user on __enter__.
  2. SecureConnection clears app.active_user on __exit__ after a normal run.
  3. SecureConnection clears app.active_user on __exit__ even when the body
     raises an exception (the exception is re-raised, not swallowed).
  4. SecureConnection with username=None does not call set_user_context but
     still calls clear_user_context on exit.
  5. The pool "checkin" event listener is registered on engines built by
     get_engine() and issues the reset SQL on every connection return.
  6. clear_user_context uses SET (not RESET) so it is safe on sessions where
     app.active_user was never previously set.

All tests use unittest.mock — no live AlloyDB connection required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest
from sqlalchemy import text

from src.security.secure_connection import SecureConnection


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_engine_and_conn() -> tuple[MagicMock, MagicMock]:
    """
    Return a mock (engine, connection) pair.

    engine.connect() returns mock_conn directly (not a context manager)
    because SecureConnection calls engine.connect() then manages its own
    lifecycle via conn.close().
    """
    mock_conn = MagicMock(name="mock_conn")
    mock_engine = MagicMock(name="mock_engine")
    mock_engine.connect.return_value = mock_conn
    return mock_engine, mock_conn


# ── SecureConnection behaviour ────────────────────────────────────────────────

class TestSecureConnectionSetsContext:
    def test_set_user_context_called_on_enter(self):
        """__enter__ must call set_user_context with the sanitised username."""
        engine, conn = _make_engine_and_conn()

        with patch("src.security.secure_connection.set_user_context") as mock_set, \
             patch("src.security.secure_connection.clear_user_context"):
            with SecureConnection(engine, "alice") as c:
                assert c is conn

            mock_set.assert_called_once_with(conn, "alice")

    def test_returns_connection_from_engine(self):
        """The yielded object is exactly what engine.connect() returned."""
        engine, conn = _make_engine_and_conn()

        with patch("src.security.secure_connection.set_user_context"), \
             patch("src.security.secure_connection.clear_user_context"):
            with SecureConnection(engine, "eve") as c:
                assert c is conn


class TestSecureConnectionClearsContext:
    def test_clear_called_after_normal_exit(self):
        """app.active_user must be cleared even when the body completes normally."""
        engine, conn = _make_engine_and_conn()

        with patch("src.security.secure_connection.set_user_context"), \
             patch("src.security.secure_connection.clear_user_context") as mock_clear:
            with SecureConnection(engine, "bob"):
                pass

            mock_clear.assert_called_once_with(conn)

    def test_clear_called_after_exception_in_body(self):
        """
        app.active_user must be cleared even when the ``with`` body raises.
        The original exception must propagate (not be swallowed).
        """
        engine, conn = _make_engine_and_conn()

        with patch("src.security.secure_connection.set_user_context"), \
             patch("src.security.secure_connection.clear_user_context") as mock_clear:
            with pytest.raises(ValueError, match="intentional"):
                with SecureConnection(engine, "carol"):
                    raise ValueError("intentional test error")

            # Clear must have run despite the exception.
            mock_clear.assert_called_once_with(conn)

    def test_conn_closed_after_normal_exit(self):
        """conn.close() must be called so the connection returns to the pool."""
        engine, conn = _make_engine_and_conn()

        with patch("src.security.secure_connection.set_user_context"), \
             patch("src.security.secure_connection.clear_user_context"):
            with SecureConnection(engine, "dave"):
                pass

        conn.close.assert_called_once()

    def test_conn_closed_after_exception_in_body(self):
        """conn.close() must be called even when the body raises."""
        engine, conn = _make_engine_and_conn()

        with patch("src.security.secure_connection.set_user_context"), \
             patch("src.security.secure_connection.clear_user_context"):
            with pytest.raises(RuntimeError):
                with SecureConnection(engine, "alice"):
                    raise RuntimeError("db exploded")

        conn.close.assert_called_once()

    def test_clear_failure_does_not_mask_body_exception(self):
        """
        If clear_user_context itself raises, the original body exception must
        still propagate — cleanup errors must never hide real errors.
        """
        engine, _ = _make_engine_and_conn()

        with patch("src.security.secure_connection.set_user_context"), \
             patch(
                 "src.security.secure_connection.clear_user_context",
                 side_effect=Exception("clear failed"),
             ):
            with pytest.raises(ValueError, match="original"):
                with SecureConnection(engine, "eve"):
                    raise ValueError("original error")


class TestSecureConnectionNoneUsername:
    def test_set_not_called_for_none_username(self):
        """With username=None, set_user_context must NOT be called."""
        engine, _ = _make_engine_and_conn()

        with patch("src.security.secure_connection.set_user_context") as mock_set, \
             patch("src.security.secure_connection.clear_user_context"):
            with SecureConnection(engine, None):
                pass

        mock_set.assert_not_called()

    def test_clear_still_called_for_none_username(self):
        """
        Even with username=None the clear step runs — guards against a
        connection that was previously used with a real user context.
        """
        engine, conn = _make_engine_and_conn()

        with patch("src.security.secure_connection.set_user_context"), \
             patch("src.security.secure_connection.clear_user_context") as mock_clear:
            with SecureConnection(engine, None):
                pass

        mock_clear.assert_called_once_with(conn)


# ── Pool checkin event ────────────────────────────────────────────────────────

class TestPoolCheckinEvent:
    """
    Verify that get_engine() registers a 'checkin' listener that resets
    app.active_user on the raw dbapi connection.

    We use a SQLite in-memory engine as a stand-in so no AlloyDB is needed.
    The listener is registered on the pool of whatever engine create_engine()
    returns — by patching create_engine we control which engine that is.
    """

    @staticmethod
    def _build_engine_via_get_engine():
        """Patch create_engine to return a real SQLite engine, call get_engine()."""
        import sqlalchemy as sa
        from unittest.mock import patch as _patch

        real_engine = sa.create_engine("sqlite:///:memory:")

        with _patch("src.config.sqlalchemy.create_engine", return_value=real_engine), \
             _patch("src.config.Config.ALLOYDB_CONN_NAME", None), \
             _patch("src.config.Config.ALLOYDB_IP", "127.0.0.1"), \
             _patch("src.config.Config.ALLOYDB_USER", "postgres"), \
             _patch("src.config.Config.ALLOYDB_PASSWORD", "test"):
            # Import happens inside the patch so get_engine uses mocked create_engine.
            from src.config import get_engine as _get
            engine = _get()

        return engine

    def test_checkin_event_registered(self):
        """
        get_engine() must register a 'checkin' pool listener.

        We verify registration behaviourally: fire the checkin event on a mock
        dbapi connection and assert that our listener executed SQL on it.
        If no listener had been registered, execute() would never be called.
        """
        engine = self._build_engine_via_get_engine()
        try:
            mock_dbapi_conn = MagicMock(name="dbapi_conn")
            mock_cursor = MagicMock(name="cursor")
            mock_dbapi_conn.cursor.return_value = mock_cursor

            engine.pool.dispatch.checkin(mock_dbapi_conn, MagicMock())

            assert mock_cursor.execute.called, (
                "pool 'checkin' listener was not registered by get_engine(): "
                "cursor.execute was never called after dispatching the event."
            )
        finally:
            engine.dispose()

    def test_checkin_resets_active_user(self):
        """
        When the checkin event fires, the listener must execute
        ``SET app.active_user = ''`` and commit on the raw dbapi connection.
        """
        engine = self._build_engine_via_get_engine()
        try:
            mock_dbapi_conn = MagicMock(name="dbapi_conn")
            mock_cursor = MagicMock(name="cursor")
            mock_dbapi_conn.cursor.return_value = mock_cursor

            # Fire the pool checkin event directly via the pool's dispatch.
            # This is the SQLAlchemy 2.x way to trigger pool events in tests.
            engine.pool.dispatch.checkin(mock_dbapi_conn, MagicMock())

            mock_cursor.execute.assert_called_once_with("SET app.active_user = ''")
            mock_dbapi_conn.commit.assert_called_once()
            mock_cursor.close.assert_called_once()
        finally:
            engine.dispose()


# ── clear_user_context uses SET not RESET ─────────────────────────────────────

class TestClearUserContextSafety:
    def test_clear_uses_set_not_reset(self):
        """
        clear_user_context must issue ``SET app.active_user = ''`` not
        ``RESET app.active_user``. RESET raises on sessions where the variable
        was never set; SET is always safe.
        """
        from src.security.context_switcher import clear_user_context

        mock_conn = MagicMock()
        clear_user_context(mock_conn)

        # Extract the SQL string that was passed to execute().
        call_args = mock_conn.execute.call_args
        assert call_args is not None, "execute() was not called"

        sql_arg = call_args[0][0]
        # text() objects compare by their string value.
        sql_str = str(sql_arg).upper()

        assert "SET" in sql_str, f"Expected SET in SQL, got: {sql_str}"
        assert "RESET" not in sql_str, (
            f"clear_user_context must not use RESET (unsafe on unset variables). "
            f"Got: {sql_str}"
        )
        assert "APP.ACTIVE_USER" in sql_str or "active_user" in str(sql_arg).lower()
