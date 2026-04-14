"""ReasoningEngine — real-time AI reasoning via AlloyDB google_ml.predict()."""

from __future__ import annotations

import structlog
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)


class ReasoningResult(BaseModel):
    """Typed result returned by the reasoning engine."""

    query: str
    answer: str
    model_id: str
    latency_ms: float
    token_count: int | None = None


class ReasoningEngine:
    """
    Executes Gemini Flash inference inside AlloyDB via google_ml.predict().

    The SQL pattern used::

        SELECT google_ml.predict(
            model_id   => :model_id,
            input      => jsonb_build_object('prompt', :prompt)
        ) AS response;

    This keeps the model call inside the database transaction — no extra
    network hop from Python to Vertex AI.

    Parameters
    ----------
    engine:
        SQLAlchemy engine connected to AlloyDB.
    model_id:
        AlloyDB-registered Gemini model ID (e.g. ``'gemini-2.0-flash-001'``).
    """

    def __init__(self, engine: Engine, model_id: str = "gemini-2.0-flash-001") -> None:
        self._engine = engine
        self._model_id = model_id

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def reason(self, prompt: str, context: str | None = None) -> ReasoningResult:
        """
        Run a single reasoning query against the registered Gemini model.

        Parameters
        ----------
        prompt:
            The user question or instruction.
        context:
            Optional additional context prepended to the prompt.

        Returns
        -------
        ReasoningResult
        """
        import time

        full_prompt = f"{context}\n\n{prompt}" if context else prompt

        sql = text("""
            SELECT
                (google_ml.predict(
                    model_id => :model_id,
                    input    => jsonb_build_object('prompt', :prompt)
                ) ->> 'text') AS answer
        """)

        log = logger.bind(model_id=self._model_id, prompt_len=len(full_prompt))
        log.info("reasoning.start")

        t0 = time.perf_counter()
        with self._engine.connect() as conn:
            row = conn.execute(sql, {"model_id": self._model_id, "prompt": full_prompt}).one()
        latency_ms = (time.perf_counter() - t0) * 1000

        log.info("reasoning.complete", latency_ms=round(latency_ms, 1))

        return ReasoningResult(
            query=prompt,
            answer=row.answer,
            model_id=self._model_id,
            latency_ms=latency_ms,
        )
