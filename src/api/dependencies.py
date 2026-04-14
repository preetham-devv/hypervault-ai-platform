"""
FastAPI dependencies shared across all routers.

Two dependencies are provided:
  - get_db_engine  — yields the singleton SQLAlchemy engine.
  - get_current_user — extracts the caller identity from the
    X-User-Identity request header.

X-User-Identity is a placeholder for real OAuth 2.0 / OIDC token
verification.  When you add an auth provider (e.g. Google IAP or Auth0),
replace the header extraction here with JWT validation — no router code
needs to change.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.engine import Engine

from src.config import get_engine

logger = logging.getLogger(__name__)

# ── Known demo users ────────────────────────────────────────────────────────
# Mirrors the USERS dict in app.py. Centralised here so the API validates
# identity claims before passing them to the RLS layer.
VALID_USERS = frozenset({"eve", "carol", "dave", "alice", "bob"})

# Default identity used when no header is supplied (e.g. internal health checks).
SYSTEM_USER = "eve"


# ── Database engine ──────────────────────────────────────────────────────────

def get_db_engine() -> Engine:
    """
    FastAPI dependency that returns the application-wide SQLAlchemy engine.

    The engine is a singleton (created once via ``@lru_cache`` in config.py)
    so this dependency is safe to inject into every request without creating
    new connection pools each time.
    """
    return get_engine()


# ── Current user / identity ──────────────────────────────────────────────────

def get_current_user(
    x_user_identity: Annotated[
        str | None,
        Header(
            alias="X-User-Identity",
            description=(
                "Caller identity used to set the PostgreSQL RLS context "
                "(app.active_user). Placeholder for OAuth 2.0 / JWT — replace "
                "with token verification before going to production."
            ),
        ),
    ] = None,
) -> str:
    """
    Extract and validate the caller's identity from the X-User-Identity header.

    Returns
    -------
    str
        Validated username that will be passed to ``set_user_context()`` as
        the PostgreSQL session variable driving RLS.

    Raises
    ------
    HTTPException 401
        If the header is present but contains an unrecognised username.
        (Missing header is allowed — falls back to SYSTEM_USER.)
    """
    if x_user_identity is None:
        # No header supplied — use a high-privilege default for backwards
        # compatibility with health checks and internal tooling.
        logger.debug("No X-User-Identity header — defaulting to '%s'", SYSTEM_USER)
        return SYSTEM_USER

    # Sanitise: strip whitespace, lowercase for case-insensitive matching.
    user = x_user_identity.strip().lower()

    if user not in VALID_USERS:
        logger.warning("Rejected unknown identity: '%s'", user)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                f"Unknown user identity '{user}'. "
                f"Valid identities: {sorted(VALID_USERS)}"
            ),
        )

    return user


# ── Convenience type aliases ─────────────────────────────────────────────────
# Import these in routers to keep function signatures concise.

DBEngine = Annotated[Engine, Depends(get_db_engine)]
CurrentUser = Annotated[str, Depends(get_current_user)]
