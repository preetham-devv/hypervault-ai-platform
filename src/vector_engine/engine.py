"""VectorEngine — batch embedding generation via AlloyDB google_ml.embedding()."""

from __future__ import annotations

import structlog
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = structlog.get_logger(__name__)


class EmbeddingResult(BaseModel):
    """Typed result for a single embedded document."""

    doc_id: str
    content: str
    embedding: list[float]
    model_id: str


class VectorEngine:
    """
    Generates and stores embeddings entirely inside AlloyDB — zero Python loops.

    The core SQL pattern::

        UPDATE documents
        SET embedding = google_ml.embedding(
            model_id => :model_id,
            content  => content
        )::vector
        WHERE embedding IS NULL
        RETURNING id, content, embedding;

    AlloyDB fans the model calls across its columnar workers; Python never
    iterates over individual rows.

    Parameters
    ----------
    engine:
        SQLAlchemy engine connected to AlloyDB.
    model_id:
        AlloyDB-registered embedding model ID (e.g. ``'text-embedding-005'``).
    """

    def __init__(self, engine: Engine, model_id: str = "text-embedding-005") -> None:
        self._engine = engine
        self._model_id = model_id

    def embed_pending(self, table: str = "documents", batch_size: int = 500) -> int:
        """
        Embed all rows where ``embedding IS NULL`` in *table*.

        No Python loop — a single UPDATE pushes all model calls into AlloyDB.

        Returns
        -------
        int
            Number of rows updated.
        """
        sql = text(f"""
            WITH updated AS (
                UPDATE {table}
                SET embedding = google_ml.embedding(
                    model_id => :model_id,
                    content  => content
                )::vector
                WHERE embedding IS NULL
                LIMIT :batch_size
                RETURNING id
            )
            SELECT count(*) AS n FROM updated;
        """)  # noqa: S608 — table name is internal, not user-supplied

        log = logger.bind(table=table, model_id=self._model_id, batch_size=batch_size)
        log.info("vector.embed_pending.start")

        with self._engine.begin() as conn:
            row = conn.execute(sql, {"model_id": self._model_id, "batch_size": batch_size}).one()

        n = int(row.n)
        log.info("vector.embed_pending.complete", rows_updated=n)
        return n

    def similarity_search(
        self,
        query: str,
        table: str = "documents",
        top_k: int = 5,
    ) -> list[dict[str, object]]:
        """
        Return the *top_k* most similar rows using cosine distance.

        The query is embedded inline via google_ml.embedding(); no separate
        embedding call needed from Python.

        Returns
        -------
        list[dict]
            Each dict contains ``id``, ``content``, and ``score``.
        """
        sql = text(f"""
            SELECT
                id,
                content,
                1 - (embedding <=> google_ml.embedding(
                    model_id => :model_id,
                    content  => :query
                )::vector) AS score
            FROM {table}
            ORDER BY embedding <=> google_ml.embedding(
                model_id => :model_id,
                content  => :query
            )::vector
            LIMIT :top_k;
        """)  # noqa: S608

        with self._engine.connect() as conn:
            rows = conn.execute(
                sql, {"model_id": self._model_id, "query": query, "top_k": top_k}
            ).fetchall()

        return [{"id": r.id, "content": r.content, "score": float(r.score)} for r in rows]
