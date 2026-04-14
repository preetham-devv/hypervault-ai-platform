"""
Tests for the reasoning engine — Gemini client and pipeline.
Uses mocked responses for unit tests (no GCP dependency).
"""

import pytest
from unittest.mock import MagicMock, patch
from src.reasoning_engine.gemini_client import GeminiClient
from src.reasoning_engine.realtime_pipeline import RealtimePipeline


class TestGeminiClient:
    @patch("src.reasoning_engine.gemini_client.Client")
    def test_generate_returns_text(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.text = "Test insight about the data"
        mock_client_cls.return_value.models.generate_content.return_value = mock_response

        client = GeminiClient(project_id="test", location="us-central1")
        result = client.generate("Analyze this data")

        assert result == "Test insight about the data"
        mock_client_cls.return_value.models.generate_content.assert_called_once()

    @patch("src.reasoning_engine.gemini_client.Client")
    def test_analyze_data_includes_context(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.text = "The engineering team has the highest salary"
        mock_client_cls.return_value.models.generate_content.return_value = mock_response

        client = GeminiClient(project_id="test", location="us-central1")
        result = client.analyze_data("dept | avg_salary\nEng | 150000", "Which dept pays most?")

        assert "salary" in result.lower()

    def test_sql_predict_generates_valid_sql(self):
        sql = GeminiClient.sql_predict("What is the average salary?")
        assert "google_ml.predict_row" in sql
        assert "gemini-2.0-flash" in sql

    def test_sql_predict_contains_input(self):
        sql = GeminiClient.sql_predict("test prompt")
        assert "test prompt" in sql


class TestRealtimePipeline:
    def test_format_data_empty(self):
        result = RealtimePipeline._format_data(["col1"], [])
        assert result == "No data returned."

    def test_format_data_with_rows(self):
        cols = ["name", "salary"]
        rows = [{"name": "Alice", "salary": 100000}]
        result = RealtimePipeline._format_data(cols, rows)
        assert "Alice" in result
        assert "100000" in result

    def test_format_data_caps_at_100(self):
        cols = ["id"]
        rows = [{"id": i} for i in range(150)]
        result = RealtimePipeline._format_data(cols, rows)
        assert "50 more rows" in result
