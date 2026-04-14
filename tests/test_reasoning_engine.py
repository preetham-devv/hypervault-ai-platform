"""Tests for reasoning_engine module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.reasoning_engine import ReasoningEngine, ReasoningResult


@pytest.fixture()
def mock_engine():
    engine = MagicMock()
    conn = MagicMock()
    engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
    engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    return engine, conn


def test_reasoning_result_model():
    result = ReasoningResult(
        query="What is AlloyDB?",
        answer="AlloyDB is a fully managed PostgreSQL-compatible database.",
        model_id="gemini-2.0-flash-001",
        latency_ms=42.5,
    )
    assert result.query == "What is AlloyDB?"
    assert result.latency_ms == 42.5
    assert result.token_count is None


def test_reason_calls_google_ml_predict(mock_engine):
    engine, conn = mock_engine

    fake_row = MagicMock()
    fake_row.answer = "AlloyDB runs ML models in-database."
    conn.execute.return_value.one.return_value = fake_row

    re = ReasoningEngine(engine, model_id="gemini-2.0-flash-001")
    result = re.reason("Explain AlloyDB ML integration")

    assert isinstance(result, ReasoningResult)
    assert result.answer == "AlloyDB runs ML models in-database."
    assert result.model_id == "gemini-2.0-flash-001"
    assert result.latency_ms >= 0

    # Verify the SQL contained google_ml.predict
    call_args = conn.execute.call_args
    sql_text = str(call_args[0][0])
    assert "google_ml.predict" in sql_text


def test_reason_prepends_context(mock_engine):
    engine, conn = mock_engine
    fake_row = MagicMock()
    fake_row.answer = "Answer with context."
    conn.execute.return_value.one.return_value = fake_row

    re = ReasoningEngine(engine)
    result = re.reason("What is it?", context="Background: AlloyDB stores embeddings.")

    params = conn.execute.call_args[0][1]
    assert "Background: AlloyDB stores embeddings." in params["prompt"]
    assert "What is it?" in params["prompt"]
