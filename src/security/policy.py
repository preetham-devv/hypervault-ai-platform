"""SecurityPolicy — AlloyDB RLS policy loader and validator."""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = structlog.get_logger(__name__)

# Tables that must have RLS enabled before the platform starts.
REQUIRED_RLS_TABLES = frozenset({"documents", "agent_sessions", "audit_log"})


class SecurityPolicy:
    """
    Validates that AlloyDB RLS policies are correctly installed.

    Call :meth:`assert_policies_installed` at application startup to fail fast
    if a table is missing its RLS policy — before any agent session opens.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def assert_policies_installed(self) -> None:
        """
        Raise ``RuntimeError`` if any required table is missing RLS.

        Checks ``pg_catalog.pg_class`` and ``pg_catalog.pg_policy`` to verify:
        - ``relrowsecurity`` is enabled on each table.
        - At least one policy exists per table.
        """
        sql = text("""
            SELECT
                c.relname                          AS table_name,
                c.relrowsecurity                   AS rls_enabled,
                count(p.polname)                   AS policy_count
            FROM pg_catalog.pg_class c
            LEFT JOIN pg_catalog.pg_policy p ON p.polrelid = c.oid
            WHERE c.relname = ANY(:tables)
              AND c.relkind = 'r'
            GROUP BY c.relname, c.relrowsecurity;
        """)

        with self._engine.connect() as conn:
            rows = conn.execute(
                sql, {"tables": list(REQUIRED_RLS_TABLES)}
            ).fetchall()

        found = {r.table_name for r in rows}
        missing_tables = REQUIRED_RLS_TABLES - found
        if missing_tables:
            raise RuntimeError(f"RLS tables not found in database: {missing_tables}")

        violations = [r for r in rows if not r.rls_enabled or r.policy_count == 0]
        if violations:
            names = [r.table_name for r in violations]
            raise RuntimeError(f"RLS not properly configured on tables: {names}")

        logger.info("security.policy.ok", tables=list(REQUIRED_RLS_TABLES))

    def list_policies(self) -> list[dict[str, object]]:
        """Return all RLS policies currently installed."""
        sql = text("""
            SELECT
                c.relname  AS table_name,
                p.polname  AS policy_name,
                p.polcmd   AS command,
                p.polpermissive AS permissive
            FROM pg_catalog.pg_policy p
            JOIN pg_catalog.pg_class c ON c.oid = p.polrelid
            ORDER BY c.relname, p.polname;
        """)
        with self._engine.connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [dict(r._mapping) for r in rows]
