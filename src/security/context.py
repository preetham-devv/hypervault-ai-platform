"""RLSContext — context manager for RLS-scoped database sessions."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from .identity import AgentIdentity

logger = structlog.get_logger(__name__)


class RLSContext:
    """
    Opens a database connection branded with agent identity settings.

    AlloyDB RLS policies read ``current_setting('app.agent_id')`` and
    ``current_setting('app.tenant_id')`` to filter rows.  This class sets
    those session-local variables at transaction start and clears them on exit.

    Usage::

        rls = RLSContext(engine)
        with rls.session(identity) as conn:
            result = conn.execute(text("SELECT * FROM documents"))
            # AlloyDB RLS silently filters to tenant rows only

    Parameters
    ----------
    engine:
        SQLAlchemy engine connected to AlloyDB.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @contextmanager
    def session(self, identity: AgentIdentity) -> Generator[Connection, None, None]:
        """
        Yield an RLS-scoped connection for *identity*.

        Raises
        ------
        ValueError
            If the identity token is expired.
        """
        if identity.is_expired:
            raise ValueError(f"AgentIdentity for '{identity.agent_id}' has expired")

        log = logger.bind(agent_id=identity.agent_id, tenant_id=identity.tenant_id)

        with self._engine.begin() as conn:
            # Brand this transaction with agent identity so RLS policies fire.
            conn.execute(
                text("""
                    SELECT
                        set_config('app.agent_id',  :agent_id,  true),
                        set_config('app.tenant_id', :tenant_id, true),
                        set_config('app.roles',     :roles,     true)
                """),
                {
                    "agent_id": identity.agent_id,
                    "tenant_id": identity.tenant_id,
                    "roles": ",".join(identity.roles),
                },
            )
            log.info("rls.session.open")
            try:
                yield conn
            finally:
                # Explicit clear — belt-and-suspenders on top of transaction rollback.
                conn.execute(
                    text("""
                        SELECT
                            set_config('app.agent_id',  '', true),
                            set_config('app.tenant_id', '', true),
                            set_config('app.roles',     '', true)
                    """)
                )
                log.info("rls.session.close")
