"""
Vector engine package — embedding generation and similarity search.

Public surface:
  VectorEngine      — batch embedding generation via AlloyDB google_ml.embedding()
                      (UPDATE SET embedding WHERE embedding IS NULL — no Python loop)
  EmbeddingResult   — typed result for a single embedded document
  VectorSearch      — cosine similarity search over pre-computed pgvector embeddings
  VectorBenchmark   — latency benchmark utility (p50/p95/p99 percentiles)
"""

from src.vector_engine.engine import EmbeddingResult, VectorEngine
from src.vector_engine.vector_search import VectorSearch
from src.vector_engine.benchmark import VectorBenchmark

__all__ = [
    "EmbeddingResult",
    "VectorEngine",
    "VectorSearch",
    "VectorBenchmark",
]
