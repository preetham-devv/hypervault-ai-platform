"""
Security package — Zero Trust RLS enforcement for AlloyDB.

Public surface:
  AgentIdentity      — typed identity token (agent_id, tenant_id, roles, expiry)
  RLSContext         — context manager that sets app.agent_id / app.tenant_id
  SecurityPolicy     — validates that required tables have RLS enabled
  SecureConnection   — context manager that sets/clears app.active_user per request
  SecureQueryExecutor — executes SQL within an RLS-enforced user context
  set_user_context   — sets app.active_user on an open connection
  get_user_context   — reads back app.active_user from the current session
  clear_user_context — resets app.active_user to an empty string
"""

from src.security.identity import AgentIdentity
from src.security.context import RLSContext
from src.security.policy import SecurityPolicy
from src.security.secure_connection import SecureConnection
from src.security.secure_query import SecureQueryExecutor
from src.security.context_switcher import (
    clear_user_context,
    get_user_context,
    set_user_context,
)

__all__ = [
    "AgentIdentity",
    "RLSContext",
    "SecurityPolicy",
    "SecureConnection",
    "SecureQueryExecutor",
    "set_user_context",
    "get_user_context",
    "clear_user_context",
]
