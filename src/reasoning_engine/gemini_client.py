"""
Gemini client — wraps Vertex AI for real-time reasoning.
Supports direct API calls and in-database inference via google_ml.predict().
"""

import logging
from typing import Optional
from google.genai import Client
from google.genai.types import GenerateContentConfig
from src.config import Config

logger = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self, project_id=None, location=None, model_id=None):
        self.project_id = project_id or Config.PROJECT_ID
        self.location = location or Config.VERTEX_REGION
        self.model_id = model_id or Config.VERTEX_MODEL
        self.client = Client(
            vertexai=True,
            project=self.project_id,
            location=self.location,
        )
        logger.info("GeminiClient ready — model=%s", self.model_id)

    def generate(self, prompt: str, system_instruction: str = None,
                 temperature: float = 0.3, max_tokens: int = 2048) -> str:
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
        system = (
            "You are an expert data analyst. You receive structured data from "
            "a production AlloyDB database and a user question. Provide concise, "
            "actionable insights with numbers and percentages. Highlight anomalies."
        )
        prompt = f"## Data\n{data_context}\n\n## Question\n{question}"
        return self.generate(prompt, system_instruction=system, temperature=0.2)

    @staticmethod
    def sql_predict(input_text: str) -> str:
        """SQL that calls Gemini INSIDE the database via google_ml."""
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
