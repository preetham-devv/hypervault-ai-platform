"""
Configuration — loads .env and provides database connection factory
using the AlloyDB Python Connector for IAM-based auth.

Connection strategy:
  - If ALLOYDB_CONNECTION_NAME is set, connects via the Cloud SQL Python
    Connector (recommended for Cloud Run / GKE — uses IAM, no IP needed).
  - Otherwise falls back to a direct TCP connection using ALLOYDB_IP
    (useful for local development with a VPN or Cloud SQL Auth Proxy).
"""

import os
from dotenv import load_dotenv
from google.cloud.alloydb.connector import Connector
import sqlalchemy
import pg8000

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
    """
    # Prefer the connector path (IAM-auth, no IP whitelisting required).
    creator = _alloydb_getconn if Config.ALLOYDB_CONN_NAME else None
    if creator:
        return sqlalchemy.create_engine(
            "postgresql+pg8000://", creator=creator,
            pool_size=5, max_overflow=2, pool_timeout=30, pool_recycle=1800,
        )
    # Fallback: direct TCP for local dev / VPN environments.
    return sqlalchemy.create_engine(
        f"postgresql+pg8000://{Config.ALLOYDB_USER}:{Config.ALLOYDB_PASSWORD}"
        f"@{Config.ALLOYDB_IP}:5432/{Config.ALLOYDB_DATABASE}",
        pool_size=5, max_overflow=2, pool_timeout=30, pool_recycle=1800,
    )


def get_raw_connection() -> pg8000.dbapi.Connection:
    """
    Return a raw pg8000 connection outside of the SQLAlchemy pool.

    Useful for operations that require direct cursor control (e.g., COPY,
    LISTEN/NOTIFY, or multi-statement scripts run from infra tooling).
    """
    if Config.ALLOYDB_CONN_NAME:
        return _alloydb_getconn()
    return _direct_getconn()
