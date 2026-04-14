"""
Gemini client — wraps Vertex AI for real-time reasoning.
Supports direct API calls and in-database inference via google_ml.predict().
"""

from __future__ import annotations

from typing import Optional

import structlog
from google.genai import Client
from google.genai.types import GenerateContentConfig
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.api.error_handlers import GeminiInferenceError
from src.config import Config

logger = structlog.get_logger(__name__)

# ── Retryable Vertex AI / google-api-core exceptions ─────────────────────────
# Imported lazily so a missing google-api-core does not break the whole module.
try:
    from google.api_core.exceptions import (  # type: ignore[import]
        DeadlineExceeded,
        InternalServerError,
        ResourceExhausted,
        ServiceUnavailable,
    )
    _RETRYABLE_EXCEPTIONS = (
        ServiceUnavailable,   # 503 — server temporarily down
        DeadlineExceeded,     # 504 — request timed out
        InternalServerError,  # 500 — transient server-side error
        ResourceExhausted,    # 429 — quota / rate-limit exceeded
    )
except ImportError:
    # If google-api-core is unavailable fall back to a safe empty tuple so
    # the retry decorator is still applied but never matches any exception.
    _RETRYABLE_EXCEPTIONS = ()  # type: ignore[assignment]

# Maximum number of inference attempts before raising GeminiInferenceError.
_MAX_ATTEMPTS = 3


class GeminiClient:
    """
    Thin wrapper around the Vertex AI Gemini API.

    Supports two inference paths:
      1. Python-side via ``generate()`` / ``analyze_data()`` — data travels
         from AlloyDB → Python → Vertex AI.
      2. In-database via ``sql_predict()`` — returns a SQL fragment that calls
         ``google_ml.predict_row()`` so Gemini runs inside AlloyDB itself.

    Transient Vertex AI errors (503, 504, 500, 429) are retried up to
    ``_MAX_ATTEMPTS`` times with exponential back-off before a
    ``GeminiInferenceError`` is raised.
    """

    def __init__(
        self,
        project_id: str | None = None,
        location: str | None = None,
        model_id: str | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        """
        Initialise the Gemini client using Vertex AI credentials.

        Parameters
        ----------
        project_id:
            GCP project ID. Defaults to ``Config.PROJECT_ID``.
        location:
            Vertex AI region (e.g. ``'us-central1'``). Defaults to
            ``Config.VERTEX_REGION``.
        model_id:
            Gemini model to use (e.g. ``'gemini-2.0-flash'``). Defaults to
            ``Config.VERTEX_MODEL``.
        timeout_seconds:
            Per-request timeout in seconds. Applied when the underlying
            SDK supports per-call timeout configuration.
        """
        self.project_id = project_id or Config.PROJECT_ID
        self.location = location or Config.VERTEX_REGION
        self.model_id = model_id or Config.VERTEX_MODEL
        self.timeout_seconds = timeout_seconds
        self.client = Client(
            vertexai=True,
            project=self.project_id,
            location=self.location,
        )
        logger.info("GeminiClient ready", model=self.model_id, timeout_s=timeout_seconds)

    # ── Private retry-decorated implementation ────────────────────────────────

    @retry(
        retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS) if _RETRYABLE_EXCEPTIONS else retry_if_exception_type(()),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        reraise=False,   # wrap exhausted retries in tenacity.RetryError
    )
    def _call_generate(
        self,
        prompt: str,
        system_instruction: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """
        Raw Gemini call with retry logic.

        Decorated with ``@retry`` so transient errors (503, 504, 500, 429)
        are retried with exponential back-off. ``reraise=False`` means that
        after ``_MAX_ATTEMPTS`` the final exception is wrapped in
        ``tenacity.RetryError`` rather than re-raised directly — the public
        ``generate()`` method converts this to ``GeminiInferenceError``.
        """
        config = GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_instruction,
        )
        response = self.client.models.generate_content(
            model=self.model_id, contents=prompt, config=config,
        )
        return response.text

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        """
        Send a prompt to Gemini and return the text response.

        Transient errors are retried up to ``_MAX_ATTEMPTS`` times. If all
        attempts fail, or if the error is permanent (bad request, permission
        denied), a ``GeminiInferenceError`` is raised.

        Parameters
        ----------
        prompt:
            The user message / query.
        system_instruction:
            Optional system prompt that shapes the model's persona and tone.
        temperature:
            Sampling temperature (0 = deterministic, 1 = creative).
        max_tokens:
            Maximum output tokens. Keeps costs predictable for large data sets.

        Returns
        -------
        str
            Raw text from the first candidate in Gemini's response.

        Raises
        ------
        GeminiInferenceError
            On any Vertex AI error — ``retryable`` is ``True`` when retries
            were exhausted, ``False`` for permanent errors.
        """
        try:
            return self._call_generate(prompt, system_instruction, temperature, max_tokens)

        except RetryError as exc:
            # All _MAX_ATTEMPTS failed with retryable exceptions.
            last = exc.last_attempt.exception()
            logger.error(
                "Gemini inference exhausted retries",
                model=self.model_id,
                attempts=_MAX_ATTEMPTS,
                last_error=str(last),
            )
            raise GeminiInferenceError(
                f"Gemini inference failed after {_MAX_ATTEMPTS} attempts: {last}",
                model=self.model_id,
                retryable=True,
                attempts=_MAX_ATTEMPTS,
            ) from exc

        except Exception as exc:
            # Non-retryable Vertex AI error or unexpected exception.
            retryable = isinstance(exc, _RETRYABLE_EXCEPTIONS) if _RETRYABLE_EXCEPTIONS else False
            logger.error(
                "Gemini inference error",
                model=self.model_id,
                retryable=retryable,
                error=str(exc),
                exc_type=type(exc).__name__,
            )
            raise GeminiInferenceError(
                str(exc),
                model=self.model_id,
                retryable=retryable,
                attempts=1,
            ) from exc

    def analyze_data(self, data_context: str, question: str) -> str:
        """
        Analyse structured AlloyDB data and answer a user question.

        A fixed system prompt configures Gemini as a data analyst that
        highlights anomalies and quantifies findings with numbers/percentages.

        Parameters
        ----------
        data_context:
            Pre-formatted table string produced by ``_format_data()``.
        question:
            The specific analysis question to answer.

        Returns
        -------
        str
            Concise, actionable insight from Gemini.
        """
        system = (
            "You are an expert data analyst. You receive structured data from "
            "a production AlloyDB database and a user question. Provide concise, "
            "actionable insights with numbers and percentages. Highlight anomalies."
        )
        prompt = f"## Data\n{data_context}\n\n## Question\n{question}"
        # Low temperature for analytical tasks — we want factual, not creative.
        return self.generate(prompt, system_instruction=system, temperature=0.2)

    @staticmethod
    def sql_predict(input_text: str) -> str:
        """
        Return a SQL fragment that calls Gemini INSIDE AlloyDB via google_ml.

        The resulting SQL can be embedded in a larger query so the model
        inference happens in the database engine — data never leaves AlloyDB.

        Parameters
        ----------
        input_text:
            The prompt text to send to the model.

        Returns
        -------
        str
            A SELECT statement using ``google_ml.predict_row()``.
        """
        return f"""
            SELECT google_ml.predict_row(
                model_id => 'gemini-2.0-flash',
                request_body => jsonb_build_object(
                    'contents', jsonb_build_array(
                        jsonb_build_object(
                            'role', 'user',
                            'parts', jsonb_build_array(
                                jsonb_build_object('text', '{input_text}')
                            )
                        )
                    )
                )
            );
        """
