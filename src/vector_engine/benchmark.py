"""
Benchmark suite — measures embedding generation throughput
and vector search latency (p50/p95/p99).
"""

import time
import structlog
from sqlalchemy import text
from src.config import get_engine

logger = structlog.get_logger(__name__)


class VectorBenchmark:
    """
    Measures AlloyDB vector search latency under realistic load.

    Runs repeated similarity searches and computes p50/p95/p99 percentiles
    so you can verify that the IVFFlat ANN index is serving sub-50ms results
    before promoting to production.
    """

    def __init__(self):
        """Connect to AlloyDB using environment config."""
        self.engine = get_engine()

    def benchmark_search(self, query: str = "senior engineer python",
                         table: str = "employees", top_k: int = 10,
                         iterations: int = 50) -> dict:
        """
        Run *iterations* similarity searches and report latency percentiles.

        All iterations reuse the same connection to avoid measuring connection
        setup time — we want to isolate query execution latency.

        Parameters
        ----------
        query:
            The search string to embed and match on each iteration.
        table:
            The AlloyDB table to search (must have an ``embedding`` column and
            a pre-built IVFFlat index for realistic ANN latency figures).
        top_k:
            Number of nearest neighbours to retrieve per query.
        iterations:
            Total number of timed query executions. Higher values give more
            stable percentile estimates (50 is a reasonable baseline).

        Returns
        -------
        dict with keys:
            ``operation``, ``iterations``, ``p50_ms``, ``p95_ms``, ``p99_ms``,
            ``min_ms``, ``max_ms``.
        """
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
        # Single connection for all iterations — measures pure query latency.
        with self.engine.connect() as conn:
            for _ in range(iterations):
                t0 = time.perf_counter()
                conn.execute(sql, {"query": query, "top_k": top_k})
                latencies.append((time.perf_counter() - t0) * 1000)

        # Sort once and use index arithmetic for O(1) percentile lookups.
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
        logger.info("Benchmark results", **result)
        return result

    def count_embeddings(self) -> dict:
        """
        Return total and embedded row counts for both core tables.

        Use this to confirm that batch embedding has completed before running
        ``benchmark_search()`` — unembedded rows are excluded from ANN queries
        (``WHERE embedding IS NOT NULL``), which would skew latency results.

        Returns
        -------
        dict with keys:
            ``employees_total``, ``employees_embedded``,
            ``reviews_total``, ``reviews_embedded``.
        """
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
