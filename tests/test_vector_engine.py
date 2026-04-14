"""Tests for vector_engine module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.vector_engine import VectorEngine


@pytest.fixture()
def mock_engine():
    engine = MagicMock()
    conn = MagicMock()
    # begin() context manager (used in embed_pending)
    engine.begin.return_value.__enter__ = MagicMock(return_value=conn)
    engine.begin.return_value.__exit__ = MagicMock(return_value=False)
    # connect() context manager (used in similarity_search)
    engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
    engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    return engine, conn


def test_embed_pending_returns_count(mock_engine):
    engine, conn = mock_engine
    fake_row = MagicMock()
    fake_row.n = 42
    conn.execute.return_value.one.return_value = fake_row

    ve = VectorEngine(engine, model_id="text-embedding-005")
    count = ve.embed_pending(table="documents", batch_size=100)

    assert count == 42

    sql_text = str(conn.execute.call_args[0][0])
    assert "google_ml.embedding" in sql_text
    assert "embedding IS NULL" in sql_text


def test_embed_pending_no_python_loop(mock_engine):
    """Verify that embed_pending issues exactly ONE SQL call (no per-row loop)."""
    engine, conn = mock_engine
    fake_row = MagicMock()
    fake_row.n = 1000
    conn.execute.return_value.one.return_value = fake_row

    ve = VectorEngine(engine)
    ve.embed_pending(batch_size=1000)

    assert conn.execute.call_count == 1, "Must be a single SQL statement, not a Python loop"


def test_similarity_search_returns_ranked_results(mock_engine):
    engine, conn = mock_engine

    def make_row(id_, content, score):
        r = MagicMock()
        r.id = id_
        r.content = content
        r.score = score
        r._mapping = {"id": id_, "content": content, "score": score}
        return r

    conn.execute.return_value.fetchall.return_value = [
        make_row("doc-1", "AlloyDB supports vector search", 0.95),
        make_row("doc-2", "Vertex AI powers Gemini", 0.88),
    ]

    ve = VectorEngine(engine)
    results = ve.similarity_search("AlloyDB vector", top_k=2)

    assert len(results) == 2
    assert results[0]["id"] == "doc-1"
    assert results[0]["score"] == pytest.approx(0.95)

    sql_text = str(conn.execute.call_args[0][0])
    assert "google_ml.embedding" in sql_text
    assert "<=>" in sql_text  # cosine distance operator
