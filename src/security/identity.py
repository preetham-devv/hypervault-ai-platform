"""AgentIdentity — signed identity token for RLS-scoped sessions."""

from __future__ import annotations

import time

from pydantic import BaseModel, Field


class AgentIdentity(BaseModel):
    """
    Represents an authenticated AI agent.

    Attributes
    ----------
    agent_id:
        Unique identifier for the agent (e.g. ``'gemini-agent-prod-01'``).
    tenant_id:
        The tenant this agent operates on behalf of.
    roles:
        List of application roles granted to this agent.
    issued_at:
        Unix timestamp when the identity was issued.
    expires_at:
        Unix timestamp after which the identity is invalid.
    """

    agent_id: str
    tenant_id: str
    roles: list[str] = Field(default_factory=list)
    issued_at: float = Field(default_factory=time.time)
    expires_at: float = Field(default_factory=lambda: time.time() + 3600)

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def has_role(self, role: str) -> bool:
        return role in self.roles
