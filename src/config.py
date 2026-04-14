"""
Configuration — loads .env and provides database connection factory
using the AlloyDB Python Connector for IAM-based auth.

Connection strategy:
  - If ALLOYDB_CONNECTION_NAME is set, connects via the Cloud SQL Python
    Connector (recommended for Cloud Run / GKE — uses IAM, no IP needed).
  - Otherwise falls back to a direct TCP connection using ALLOYDB_IP
    (useful for local development with a VPN or Cloud SQL Auth Proxy).
"""

import logging
import os
from dotenv import load_dotenv
from google.cloud.alloydb.connector import Connector
import sqlalchemy
from sqlalchemy import event
import pg8000

_logger = logging.getLogger(__name__)

load_dotenv()


class Config:
    """Central store for all environment-driven settings."""

    # ── Google Cloud project & region ──
    PROJECT_ID          = os.getenv("GOOGLE_CLOUD_PROJECT")
    LOCATION            = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    # ── AlloyDB cluster / instance identifiers ──
    ALLOYDB_CLUSTER     = os.getenv("ALLOYDB_CLUSTER")
    ALLOYDB_INSTANCE    = os.getenv("ALLOYDB_INSTANCE")
    ALLOYDB_REGION      = os.getenv("ALLOYDB_REGION", "us-central1")

    # ── AlloyDB connection parameters ──
    ALLOYDB_DATABASE    = os.getenv("ALLOYDB_DATABASE", "hr_platform")
    ALLOYDB_USER        = os.getenv("ALLOYDB_USER", "postgres")
    ALLOYDB_PASSWORD    = os.getenv("ALLOYDB_PASSWORD")
    ALLOYDB_IP          = os.getenv("ALLOYDB_IP")           # direct TCP (dev only)
    ALLOYDB_CONN_NAME   = os.getenv("ALLOYDB_CONNECTION_NAME")  # Cloud SQL Connector URI

    # ── Vertex AI / Gemini settings ──
    VERTEX_MODEL        = os.getenv("VERTEX_AI_MODEL", "gemini-2.0-flash")
    VERTEX_EMBED_MODEL  = os.getenv("VERTEX_AI_EMBEDDING_MODEL", "text-embedding-005")
    VERTEX_REGION       = os.getenv("VERTEX_AI_ENDPOINT_REGION", "us-central1")

    # ── API layer ──
    # Streamlit calls FastAPI via this base URL. In the Docker container both
    # processes share localhost; in local dev both run on the same machine.
    API_BASE_URL        = os.getenv("API_BASE_URL", "http://localhost:8080")

    # ── Application settings ──
    APP_ENV             = os.getenv("APP_ENV", "development")
    LOG_LEVEL           = os.getenv("LOG_LEVEL", "INFO")


# Module-level singleton — reused across all connection factory calls.
_connector = None


def _get_connector() -> Connector:
    """Return (or lazily create) the shared Cloud SQL Python Connector instance."""
    global _connector
    if _connector is None:
        _connector = Connector()
    return _connector


def _alloydb_getconn() -> pg8000.dbapi.Connection:
    """
    Open a connection through the Cloud SQL Python Connector.

    Credentials are sourced from Application Default Credentials — no password
    is embedded in the connection string.
    """
    return _get_connector().connect(
        instance_uri=Config.ALLOYDB_CONN_NAME,
        driver="pg8000",
        user=Config.ALLOYDB_USER,
        password=Config.ALLOYDB_PASSWORD,
        db=Config.ALLOYDB_DATABASE,
    )


def _direct_getconn() -> pg8000.dbapi.Connection:
    """
    Open a direct TCP connection to AlloyDB.

    Used in local development when ALLOYDB_IP is set and no Cloud SQL
    Connector URI is configured.
    """
    return pg8000.connect(
        host=Config.ALLOYDB_IP, port=5432,
        user=Config.ALLOYDB_USER, password=Config.ALLOYDB_PASSWORD,
        database=Config.ALLOYDB_DATABASE,
    )


def get_engine() -> sqlalchemy.engine.Engine:
    """
    Build and return a SQLAlchemy connection pool for AlloyDB.

    Chooses the Cloud SQL Connector path when ALLOYDB_CONNECTION_NAME is set,
    otherwise falls back to a direct TCP URL. Pool is sized conservatively
    (5 + 2 overflow) and recycles connections after 30 min to avoid stale
    sockets on Cloud Run instances that may have been idle.

    Safety measures applied to every engine:
      - ``pool_pre_ping=True``: issues a ``SELECT 1`` before handing a pooled
        connection to a caller, discarding dead sockets transparently.
      - ``checkin`` event listener: resets ``app.active_user`` to an empty
        string every time a connection is returned to the pool, preventing
        RLS session variable leakage between requests / users.
    """
    _pool_kwargs = dict(
        pool_size=5,
        max_overflow=2,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,      # discard stale connections silently
    )

    # Prefer the connector path (IAM-auth, no IP whitelisting required).
    if Config.ALLOYDB_CONN_NAME:
        engine = sqlalchemy.create_engine(
            "postgresql+pg8000://", creator=_alloydb_getconn, **_pool_kwargs
        )
    else:
        # Fallback: direct TCP for local dev / VPN environments.
        engine = sqlalchemy.create_engine(
            f"postgresql+pg8000://{Config.ALLOYDB_USER}:{Config.ALLOYDB_PASSWORD}"
            f"@{Config.ALLOYDB_IP}:5432/{Config.ALLOYDB_DATABASE}",
            **_pool_kwargs,
        )

    @event.listens_for(engine, "checkin")
    def _reset_rls_context(
        dbapi_conn: pg8000.dbapi.Connection,
        connection_record: object,
    ) -> None:
        """
        Second line of defence: clear ``app.active_user`` when a connection
        is returned to the pool.

        This fires *after* SQLAlchemy has already rolled back any open
        transaction on the connection, so we start from a clean state.
        We still commit the SET to avoid leaving an implicit open transaction
        on pg8000's non-autocommit connection.

        If this reset fails for any reason (e.g. the connection is already
        broken) the exception is caught and logged so it never prevents the
        connection from being checked back in.
        """
        cursor = dbapi_conn.cursor()
        try:
            # SET rather than RESET — safe even if the variable was never set
            # in this session (RESET raises on unknown custom parameters).
            cursor.execute("SET app.active_user = ''")
            dbapi_conn.commit()
            _logger.debug("pool checkin: app.active_user cleared")
        except Exception:
            _logger.warning(
                "pool checkin: failed to reset app.active_user — "
                "rolling back to keep connection clean",
                exc_info=True,
            )
            try:
                dbapi_conn.rollback()
            except Exception:
                pass  # Connection is broken; pool will discard it
        finally:
            cursor.close()

    return engine


def get_raw_connection() -> pg8000.dbapi.Connection:
    """
    Return a raw pg8000 connection outside of the SQLAlchemy pool.

    Useful for operations that require direct cursor control (e.g., COPY,
    LISTEN/NOTIFY, or multi-statement scripts run from infra tooling).
    """
    if Config.ALLOYDB_CONN_NAME:
        return _alloydb_getconn()
    return _direct_getconn()
