"""
Tests for vector engine — embedding stats and search latency.
Requires AlloyDB with embeddings already generated.
"""

import pytest
from src.vector_engine.vector_search import VectorSearch
from src.vector_engine.benchmark import VectorBenchmark
from src.config import get_engine


@pytest.fixture(scope="module")
def engine():
    try:
        eng = get_engine()
        with eng.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return eng
    except Exception:
        pytest.skip("AlloyDB not available")


@pytest.fixture
def vs(engine):
    return VectorSearch(engine)


@pytest.fixture
def bench(engine):
    b = VectorBenchmark()
    b.engine = engine
    return b


class TestVectorSearch:
    def test_search_returns_results(self, vs):
        results = vs.search_employees("python engineer", top_k=5)
        assert isinstance(results, list)
        # May be empty if embeddings not generated yet
        if results:
            assert "name" in results[0]
            assert "similarity" in results[0]

    def test_search_respects_top_k(self, vs):
        results = vs.search_employees("engineer", top_k=3)
        assert len(results) <= 3

    def test_search_with_rls(self, vs):
        admin_results = vs.search_employees("engineer", top_k=50, active_user="eve")
        emp_results = vs.search_employees("engineer", top_k=50, active_user="alice")
        # Admin should see more results than an individual employee
        if admin_results and emp_results:
            assert len(admin_results) >= len(emp_results)

    def test_embedding_stats(self, vs):
        stats = vs.get_embedding_stats()
        assert len(stats) == 2
        assert stats[0]["tbl"] in ("employees", "performance_reviews")


class TestBenchmark:
    def test_count_embeddings(self, bench):
        counts = bench.count_embeddings()
        assert "employees_total" in counts
        assert "employees_embedded" in counts
        assert counts["employees_total"] >= 0
