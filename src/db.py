"""Database connection factory for AlloyDB via Cloud SQL Python Connector."""

from __future__ import annotations

from functools import lru_cache

import pg8000
import structlog
from google.cloud.sql.connector import Connector
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.pool import QueuePool

logger = structlog.get_logger(__name__)


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    alloydb_project_id: str
    alloydb_region: str = "us-central1"
    alloydb_cluster: str
    alloydb_instance: str
    alloydb_database: str = "ai_platform"
    alloydb_user: str
    alloydb_password: str

    @property
    def instance_connection_name(self) -> str:
        return (
            f"{self.alloydb_project_id}:"
            f"{self.alloydb_region}:"
            f"{self.alloydb_cluster}:{self.alloydb_instance}"
        )


@lru_cache(maxsize=1)
def get_engine(pool_size: int = 5, max_overflow: int = 10) -> Engine:
    """
    Return a singleton SQLAlchemy engine connected to AlloyDB.

    Uses the Cloud SQL Python Connector so credentials are handled by
    Application Default Credentials — no password in the connection string.
    """
    settings = DatabaseSettings()  # type: ignore[call-arg]
    connector = Connector()

    def getconn() -> pg8000.dbapi.Connection:
        return connector.connect(
            settings.instance_connection_name,
            "pg8000",
            user=settings.alloydb_user,
            password=settings.alloydb_password,
            db=settings.alloydb_database,
        )

    engine = create_engine(
        "postgresql+pg8000://",
        creator=getconn,
        poolclass=QueuePool,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def set_search_path(dbapi_conn: pg8000.dbapi.Connection, _: object) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("SET search_path TO public, google_ml")
        cursor.close()

    logger.info("db.engine.created", instance=settings.instance_connection_name)
    return engine
