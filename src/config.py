"""
Configuration — loads .env and provides database connection factory
using the AlloyDB Python Connector for IAM-based auth.
"""

import os
from dotenv import load_dotenv
from google.cloud.alloydb.connector import Connector
import sqlalchemy
import pg8000

load_dotenv()


class Config:
    PROJECT_ID          = os.getenv("GOOGLE_CLOUD_PROJECT")
    LOCATION            = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    ALLOYDB_CLUSTER     = os.getenv("ALLOYDB_CLUSTER")
    ALLOYDB_INSTANCE    = os.getenv("ALLOYDB_INSTANCE")
    ALLOYDB_REGION      = os.getenv("ALLOYDB_REGION", "us-central1")
    ALLOYDB_DATABASE    = os.getenv("ALLOYDB_DATABASE", "hr_platform")
    ALLOYDB_USER        = os.getenv("ALLOYDB_USER", "postgres")
    ALLOYDB_PASSWORD    = os.getenv("ALLOYDB_PASSWORD")
    ALLOYDB_IP          = os.getenv("ALLOYDB_IP")
    ALLOYDB_CONN_NAME   = os.getenv("ALLOYDB_CONNECTION_NAME")
    VERTEX_MODEL        = os.getenv("VERTEX_AI_MODEL", "gemini-2.0-flash")
    VERTEX_EMBED_MODEL  = os.getenv("VERTEX_AI_EMBEDDING_MODEL", "text-embedding-005")
    VERTEX_REGION       = os.getenv("VERTEX_AI_ENDPOINT_REGION", "us-central1")
    APP_ENV             = os.getenv("APP_ENV", "development")
    LOG_LEVEL           = os.getenv("LOG_LEVEL", "INFO")


_connector = None


def _get_connector():
    global _connector
    if _connector is None:
        _connector = Connector()
    return _connector


def _alloydb_getconn():
    return _get_connector().connect(
        instance_uri=Config.ALLOYDB_CONN_NAME,
        driver="pg8000",
        user=Config.ALLOYDB_USER,
        password=Config.ALLOYDB_PASSWORD,
        db=Config.ALLOYDB_DATABASE,
    )


def _direct_getconn():
    return pg8000.connect(
        host=Config.ALLOYDB_IP, port=5432,
        user=Config.ALLOYDB_USER, password=Config.ALLOYDB_PASSWORD,
        database=Config.ALLOYDB_DATABASE,
    )


def get_engine() -> sqlalchemy.engine.Engine:
    creator = _alloydb_getconn if Config.ALLOYDB_CONN_NAME else None
    if creator:
        return sqlalchemy.create_engine(
            "postgresql+pg8000://", creator=creator,
            pool_size=5, max_overflow=2, pool_timeout=30, pool_recycle=1800,
        )
    return sqlalchemy.create_engine(
        f"postgresql+pg8000://{Config.ALLOYDB_USER}:{Config.ALLOYDB_PASSWORD}"
        f"@{Config.ALLOYDB_IP}:5432/{Config.ALLOYDB_DATABASE}",
        pool_size=5, max_overflow=2, pool_timeout=30, pool_recycle=1800,
    )


def get_raw_connection():
    if Config.ALLOYDB_CONN_NAME:
        return _alloydb_getconn()
    return _direct_getconn()
