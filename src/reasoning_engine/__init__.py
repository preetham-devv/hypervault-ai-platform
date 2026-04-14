"""
Reasoning engine package — Gemini-powered data analysis and pipeline.

Public surface:
  ReasoningEngine    — executes Gemini inside AlloyDB via google_ml.predict()
                       (inference happens in-database; no Python ↔ Vertex AI hop)
  ReasoningResult    — typed result (query, answer, model_id, latency_ms, token_count)
  GeminiClient       — Python-side Vertex AI wrapper with tenacity retry logic
  RealtimePipeline   — orchestrates AlloyDB → Gemini reasoning loop under RLS
  SustainabilityAnalyzer — domain-specific ESG reasoning (carbon footprint, reports)
"""

from src.reasoning_engine.engine import ReasoningEngine, ReasoningResult
from src.reasoning_engine.gemini_client import GeminiClient
from src.reasoning_engine.realtime_pipeline import RealtimePipeline
from src.reasoning_engine.sustainability_analyzer import SustainabilityAnalyzer

__all__ = [
    "GeminiClient",
    "RealtimePipeline",
    "ReasoningEngine",
    "ReasoningResult",
    "SustainabilityAnalyzer",
]
