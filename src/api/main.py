"""
HyperVault AI Platform — FastAPI application entry point.

Startup sequence (lifespan):
  1. configure_logging()    — structlog JSON/console setup
  2. get_engine()           — SQLAlchemy pool, AlloyDB smoke-test
  3. setup_tracing(engine)  — OTel TracerProvider + SQLAlchemy instrumentation
  4. setup_metrics()        — OTel MeterProvider + instrument registration
  5. FastAPIInstrumentor    — auto-instrument every endpoint with trace spans

Exposed at :8080 (Cloud Run ingress port).
Streamlit dashboard runs at :8501 and calls this API via localhost.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.error_handlers import register_error_handlers
from src.api.routers import reasoning, search, security, sustainability
from src.api.schemas import HealthResponse
from src.config import get_engine
from src.observability.logging_config import configure_logging, RequestIDMiddleware
from src.observability.tracing import setup_tracing
from src.observability.metrics import setup_metrics

# Logging must be configured before the first log call so that the stdlib
# bridge is in place when uvicorn emits its startup messages.
configure_logging()
logger = structlog.get_logger(__name__)

# Version is read from the environment so Cloud Build can inject it at build
# time without modifying source files.
_VERSION = os.getenv("APP_VERSION", "0.1.0")


# =============================================================================
# Lifespan — startup / shutdown
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Manage resources that must exist for the full lifetime of the application.

    On startup:
      - Creates the SQLAlchemy connection pool and verifies AlloyDB is reachable.
      - Attaches the engine to ``app.state`` so ``get_db_engine`` can return it.

    On shutdown:
      - Calls ``engine.dispose()`` to close all pooled connections gracefully,
        preventing "too many clients" errors in AlloyDB after a rolling deploy.
    """
    logger.info("HyperVault API starting up", version=_VERSION)
    engine = get_engine()

    # Smoke-test the connection so a misconfigured .env fails fast at startup
    # rather than on the first request in production.
    try:
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        logger.info("AlloyDB connectivity verified")
    except Exception as exc:
        # Log the error but don't crash — health check will surface it.
        logger.error("AlloyDB connectivity check failed", error=str(exc))

    app.state.engine = engine

    # Tracing must be set up after the engine exists so SQLAlchemy
    # instrumentation can be attached in the same call.
    setup_tracing(engine)
    setup_metrics()

    # Auto-instrument all FastAPI endpoints — must be called after app is
    # created but before the first request is served.
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore[import]
        FastAPIInstrumentor.instrument_app(app)
        logger.info("OTel: FastAPI instrumentation enabled")
    except ImportError:
        logger.warning(
            "opentelemetry-instrumentation-fastapi not installed — "
            "endpoint spans will not be emitted"
        )

    yield  # Application is running

    logger.info("HyperVault API shutting down — disposing connection pool")
    engine.dispose()


# =============================================================================
# Application factory
# =============================================================================

app = FastAPI(
    title="HyperVault AI Platform API",
    description=(
        "REST API layer between the Streamlit dashboard and AlloyDB. "
        "Every endpoint enforces row-level security via the X-User-Identity "
        "header before touching the database."
    ),
    version=_VERSION,
    lifespan=lifespan,
    docs_url="/docs",       # Swagger UI
    redoc_url="/redoc",     # ReDoc
    openapi_url="/openapi.json",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
# Streamlit runs on :8501 in the same container; allow it plus any local dev
# origins. Restrict ``allow_origins`` to your actual domain in production.
_CORS_ORIGINS = [
    "http://localhost:8501",   # Streamlit (local dev)
    "http://localhost:8080",   # FastAPI itself (for curl / Swagger)
    "http://127.0.0.1:8501",
    "http://127.0.0.1:8080",
]

# Add the deployed Cloud Run URL if set at runtime.
if cloud_run_url := os.getenv("CLOUD_RUN_URL"):
    _CORS_ORIGINS.append(cloud_run_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Bind a UUID request_id to every structlog event for the lifetime of each
# request, and echo it back in the X-Request-ID response header.
app.add_middleware(RequestIDMiddleware)

# Register domain exception → HTTP status code mappings.
register_error_handlers(app)

# ── Routers ───────────────────────────────────────────────────────────────────
_API_PREFIX = "/api/v1"

app.include_router(reasoning.router,     prefix=_API_PREFIX)
app.include_router(search.router,        prefix=_API_PREFIX)
app.include_router(security.router,      prefix=_API_PREFIX)
app.include_router(sustainability.router, prefix=_API_PREFIX)


# =============================================================================
# Health check
# =============================================================================

@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Liveness probe",
    description=(
        "Returns 200 OK when the API process is running. "
        "Does NOT verify AlloyDB connectivity — use /readyz for that."
    ),
)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=_VERSION)


@app.get(
    "/readyz",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Readiness probe",
    description="Returns 200 OK only when AlloyDB is reachable.",
)
def readyz() -> HealthResponse:
    """
    Verify the database connection is alive before reporting ready.

    Cloud Run readiness probes call this endpoint; if it returns non-200
    the instance is taken out of rotation until AlloyDB recovers.
    """
    import sqlalchemy
    try:
        with app.state.engine.connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 1"))
    except Exception as exc:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AlloyDB not reachable: {exc}",
        ) from exc

    return HealthResponse(status="ready", version=_VERSION)
