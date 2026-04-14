"""
Vector search — cosine similarity against AlloyDB embeddings.
Queries are embedded on-the-fly and matched against pre-computed vectors.
"""

import logging
from typing import Optional
import sqlalchemy
from sqlalchemy import text
from src.config import get_engine
from src.security.context_switcher import set_user_context

logger = logging.getLogger(__name__)


class VectorSearch:
    def __init__(self, engine: sqlalchemy.engine.Engine = None):
        self.engine = engine or get_engine()

    def search_employees(self, query: str, top_k: int = 10,
                         active_user: Optional[str] = None) -> list[dict]:
        sql = text("""
            SELECT e.id, e.name, e.department, e.role, e.salary,
                   1 - (e.embedding <=> google_ml.embedding(
                       model_id => 'text-embedding-005', content => :query
                   )::vector) AS similarity
            FROM employees e
            WHERE e.embedding IS NOT NULL
            ORDER BY e.embedding <=> google_ml.embedding(
                model_id => 'text-embedding-005', content => :query
            )::vector
            LIMIT :top_k;
        """)
        with self.engine.connect() as conn:
            if active_user:
                set_user_context(conn, active_user)
            result = conn.execute(sql, {"query": query, "top_k": top_k})
            cols = list(result.keys())
            rows = [dict(zip(cols, r)) for r in result.fetchall()]
        logger.info("Vector search: '%s' → %d results", query[:40], len(rows))
        return rows

    def search_reviews(self, query: str, top_k: int = 10,
                       active_user: Optional[str] = None) -> list[dict]:
        sql = text("""
            SELECT pr.id, e.name, pr.rating, pr.review_text, pr.review_date,
                   1 - (pr.embedding <=> google_ml.embedding(
                       model_id => 'text-embedding-005', content => :query
                   )::vector) AS similarity
            FROM performance_reviews pr
            JOIN employees e ON e.id = pr.employee_id
            WHERE pr.embedding IS NOT NULL
            ORDER BY pr.embedding <=> google_ml.embedding(
                model_id => 'text-embedding-005', content => :query
            )::vector
            LIMIT :top_k;
        """)
        with self.engine.connect() as conn:
            if active_user:
                set_user_context(conn, active_user)
            result = conn.execute(sql, {"query": query, "top_k": top_k})
            cols = list(result.keys())
            return [dict(zip(cols, r)) for r in result.fetchall()]

    def get_embedding_stats(self) -> list[dict]:
        sql = text("""
            SELECT 'employees' AS tbl, COUNT(*) AS total,
                   COUNT(embedding) AS embedded
            FROM employees
            UNION ALL
            SELECT 'performance_reviews', COUNT(*), COUNT(embedding)
            FROM performance_reviews;
        """)
        with self.engine.connect() as conn:
            result = conn.execute(sql)
            return [dict(zip(result.keys(), r)) for r in result.fetchall()]
