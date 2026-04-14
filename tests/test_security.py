"""Tests for security module."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, call

import pytest

from src.security import AgentIdentity, RLSContext, SecurityPolicy


# ---------------------------------------------------------------------------
# AgentIdentity
# ---------------------------------------------------------------------------

def test_agent_identity_defaults():
    identity = AgentIdentity(agent_id="agent-01", tenant_id="tenant-acme")
    assert not identity.is_expired
    assert identity.roles == []


def test_agent_identity_expiry():
    identity = AgentIdentity(
        agent_id="agent-01",
        tenant_id="tenant-acme",
        expires_at=time.time() - 1,  # already expired
    )
    assert identity.is_expired


def test_has_role():
    identity = AgentIdentity(
        agent_id="a", tenant_id="t", roles=["reader", "writer"]
    )
    assert identity.has_role("reader")
    assert not identity.has_role("admin")


# ---------------------------------------------------------------------------
# RLSContext
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_engine():
    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__ = MagicMock(return_value=conn)
    engine.begin.return_value.__exit__ = MagicMock(return_value=False)
    return engine, conn


def test_rls_context_sets_session_variables(mock_engine):
    engine, conn = mock_engine
    identity = AgentIdentity(agent_id="agent-x", tenant_id="tenant-y", roles=["reader"])

    rls = RLSContext(engine)
    with rls.session(identity) as c:
        assert c is conn

    # First execute call must set app.agent_id and app.tenant_id
    first_call_params = conn.execute.call_args_list[0][0][1]
    assert first_call_params["agent_id"] == "agent-x"
    assert first_call_params["tenant_id"] == "tenant-y"
    assert "reader" in first_call_params["roles"]


def test_rls_context_clears_on_exit(mock_engine):
    engine, conn = mock_engine
    identity = AgentIdentity(agent_id="a", tenant_id="t")

    rls = RLSContext(engine)
    with rls.session(identity):
        pass

    # context.py embeds empty strings directly in the SQL via set_config('app.agent_id', '', true)
    # rather than bind parameters, so we verify the SQL text of the last execute call.
    assert conn.execute.call_count >= 2, "Expected at least two execute calls (set + clear)"
    last_sql = str(conn.execute.call_args_list[-1][0][0])
    assert "set_config" in last_sql, f"Expected set_config in clear SQL, got: {last_sql}"
    # The clear SQL must pass empty strings for agent_id and tenant_id.
    assert "''" in last_sql, f"Expected empty-string literals in clear SQL, got: {last_sql}"


def test_rls_context_rejects_expired_identity(mock_engine):
    engine, _ = mock_engine
    identity = AgentIdentity(
        agent_id="a", tenant_id="t", expires_at=time.time() - 10
    )

    rls = RLSContext(engine)
    with pytest.raises(ValueError, match="expired"):
        with rls.session(identity):
            pass


# ---------------------------------------------------------------------------
# SecurityPolicy
# ---------------------------------------------------------------------------

def test_policy_raises_on_missing_table():
    engine = MagicMock()
    conn = MagicMock()
    engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
    engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    # Return only one of the required tables
    row = MagicMock()
    row.table_name = "documents"
    row.rls_enabled = True
    row.policy_count = 1
    conn.execute.return_value.fetchall.return_value = [row]

    policy = SecurityPolicy(engine)
    with pytest.raises(RuntimeError, match="not found"):
        policy.assert_policies_installed()


def test_policy_raises_on_missing_rls():
    engine = MagicMock()
    conn = MagicMock()
    engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
    engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    rows = []
    for name in ("documents", "agent_sessions", "audit_log"):
        r = MagicMock()
        r.table_name = name
        r.rls_enabled = name != "documents"  # documents has RLS disabled
        r.policy_count = 1
        rows.append(r)
    conn.execute.return_value.fetchall.return_value = rows

    policy = SecurityPolicy(engine)
    with pytest.raises(RuntimeError, match="not properly configured"):
        policy.assert_policies_installed()
