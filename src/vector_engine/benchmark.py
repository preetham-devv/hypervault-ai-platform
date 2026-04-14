"""
Benchmark suite — measures embedding generation throughput
and vector search latency (p50/p95/p99).
"""

import time
import logging
from sqlalchemy import text
from src.config import get_engine

logger = logging.getLogger(__name__)


class VectorBenchmark:
    def __init__(self):
        self.engine = get_engine()

    def benchmark_search(self, query: str = "senior engineer python",
                         table: str = "employees", top_k: int = 10,
                         iterations: int = 50) -> dict:
        sql = text(f"""
            SELECT id, 1 - (embedding <=> google_ml.embedding(
                model_id => 'text-embedding-005', content => :query
            )::vector) AS score
            FROM {table} WHERE embedding IS NOT NULL
            ORDER BY embedding <=> google_ml.embedding(
                model_id => 'text-embedding-005', content => :query
            )::vector LIMIT :top_k;
        """)

        latencies = []
        with self.engine.connect() as conn:
            for _ in range(iterations):
                t0 = time.perf_counter()
                conn.execute(sql, {"query": query, "top_k": top_k})
                latencies.append((time.perf_counter() - t0) * 1000)

        latencies.sort()
        n = len(latencies)
        result = {
            "operation": "similarity_search",
            "iterations": iterations,
            "p50_ms": round(latencies[n // 2], 2),
            "p95_ms": round(latencies[int(n * 0.95)], 2),
            "p99_ms": round(latencies[int(n * 0.99)], 2),
            "min_ms": round(latencies[0], 2),
            "max_ms": round(latencies[-1], 2),
        }
        logger.info("Benchmark results: %s", result)
        return result

    def count_embeddings(self) -> dict:
        with self.engine.connect() as conn:
            emp = conn.execute(text(
                "SELECT COUNT(*), COUNT(embedding) FROM employees"
            )).fetchone()
            rev = conn.execute(text(
                "SELECT COUNT(*), COUNT(embedding) FROM performance_reviews"
            )).fetchone()
        return {
            "employees_total": emp[0], "employees_embedded": emp[1],
            "reviews_total": rev[0], "reviews_embedded": rev[1],
        }
