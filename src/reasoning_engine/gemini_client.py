"""
Gemini client — wraps Vertex AI for real-time reasoning.
Supports direct API calls and in-database inference via google_ml.predict().
"""

from typing import Optional
import structlog
from google.genai import Client
from google.genai.types import GenerateContentConfig
from src.config import Config

logger = structlog.get_logger(__name__)


class GeminiClient:
    """
    Thin wrapper around the Vertex AI Gemini API.

    Supports two inference paths:
      1. Python-side via ``generate()`` / ``analyze_data()`` — data travels
         from AlloyDB → Python → Vertex AI.
      2. In-database via ``sql_predict()`` — returns a SQL fragment that calls
         ``google_ml.predict_row()`` so Gemini runs inside AlloyDB itself.
    """

    def __init__(self, project_id=None, location=None, model_id=None):
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
        """
        self.project_id = project_id or Config.PROJECT_ID
        self.location = location or Config.VERTEX_REGION
        self.model_id = model_id or Config.VERTEX_MODEL
        self.client = Client(
            vertexai=True,
            project=self.project_id,
            location=self.location,
        )
        logger.info("GeminiClient ready", model=self.model_id)

    def generate(self, prompt: str, system_instruction: str = None,
                 temperature: float = 0.3, max_tokens: int = 2048) -> str:
        """
        Send a prompt to Gemini and return the text response.

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
