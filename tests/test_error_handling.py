"""
Tests for production error handling.

Coverage:
  1. GeminiClient retry — retries 3x on transient errors, succeeds on 3rd attempt.
  2. GeminiClient retry exhausted — GeminiInferenceError raised with retryable=True.
  3. GeminiClient non-retryable error — GeminiInferenceError raised without retrying.
  4. HTTP 502 for GeminiInferenceError — registered handler returns correct shape.
  5. HTTP 502 for VectorSearchError — registered handler returns correct shape.
  6. HTTP 500 for RLSViolationError — registered handler returns correct shape.
  7. HTTP 503 for DatabaseConnectionError — registered handler returns correct shape.
  8. correlation_id is present in every error response.
  9. VectorSearchError raised when embedding column missing.
  10. RLSViolationError raised when SET app.active_user fails.
  11. RLSViolationError raised when CLEAR app.active_user fails.

All tests use unittest.mock — no live AlloyDB or Vertex AI required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest
import sqlalchemy.exc
from fastapi.testclient import TestClient

from src.api.error_handlers import (
    DatabaseConnectionError,
    GeminiInferenceError,
    HyperVaultError,
    RLSViolationError,
    VectorSearchError,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture()
def test_client():
    """
    TestClient with all external dependencies mocked so no network calls occur.

    - get_engine() returns a MagicMock engine whose connect() context manager
      succeeds silently (satisfies the startup smoke-test in lifespan).
    - setup_tracing and setup_metrics are no-ops.
    - FastAPIInstrumentor is patched to prevent OTel initialisation.
    """
    mock_engine = MagicMock(name="mock_engine")
    # Make engine.connect() work as a context manager for the smoke-test.
    mock_conn = MagicMock(name="mock_conn")
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    with (
        patch("src.config.get_engine", return_value=mock_engine),
        patch("src.observability.tracing.setup_tracing"),
        patch("src.observability.metrics.setup_metrics"),
        # opentelemetry-instrumentation-fastapi is an optional production
        # dependency not installed in the test venv. main.py already guards
        # with try/except ImportError, so no patching is needed here.
    ):
        from src.api.main import app
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client


def _gemini_client_stub() -> "GeminiClient":
    """
    Return a GeminiClient with no real Vertex AI connection.

    Uses __new__ to skip __init__ so no network calls are made.
    """
    from src.reasoning_engine.gemini_client import GeminiClient
    obj = GeminiClient.__new__(GeminiClient)
    obj.model_id = "gemini-2.0-flash"
    obj.timeout_seconds = 30
    obj.client = MagicMock(name="mock_genai_client")
    return obj


# =============================================================================
# GeminiClient retry behaviour
# =============================================================================

class TestGeminiRetry:
    @patch("time.sleep")  # prevent real waiting between retry attempts
    def test_retries_on_transient_error_succeeds_on_third(self, _mock_sleep):
        """
        generate() retries twice after ServiceUnavailable then returns the
        successful response from the third attempt.
        """
        try:
            from google.api_core.exceptions import ServiceUnavailable
        except ImportError:
            pytest.skip("google-api-core not installed")

        client = _gemini_client_stub()
        call_count = 0

        def flaky(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ServiceUnavailable("server unavailable")
            mock_response = MagicMock()
            mock_response.text = "analysis result"
            return mock_response

        client.client.models.generate_content.side_effect = flaky

        result = client.generate("test prompt")

        assert result == "analysis result"
        assert call_count == 3, f"Expected 3 calls, got {call_count}"

    @patch("time.sleep")
    def test_retries_on_resource_exhausted(self, _mock_sleep):
        """
        generate() retries on ResourceExhausted (429 rate-limit) in the same
        way as on ServiceUnavailable.
        """
        try:
            from google.api_core.exceptions import ResourceExhausted
        except ImportError:
            pytest.skip("google-api-core not installed")

        client = _gemini_client_stub()
        call_count = 0

        def rate_limited(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ResourceExhausted("quota exceeded")
            resp = MagicMock()
            resp.text = "ok"
            return resp

        client.client.models.generate_content.side_effect = rate_limited

        result = client.generate("query")
        assert result == "ok"
        assert call_count == 2

    @patch("time.sleep")
    def test_raises_gemini_inference_error_after_all_retries(self, _mock_sleep):
        """
        When all three attempts fail with a transient error, GeminiInferenceError
        is raised with retryable=True and attempts=3.
        """
        try:
            from google.api_core.exceptions import ServiceUnavailable
        except ImportError:
            pytest.skip("google-api-core not installed")

        client = _gemini_client_stub()
        client.client.models.generate_content.side_effect = ServiceUnavailable("down")

        with pytest.raises(GeminiInferenceError) as exc_info:
            client.generate("test prompt")

        err = exc_info.value
        assert err.retryable is True
        assert err.attempts == 3
        assert err.model == "gemini-2.0-flash"
        # Verify all 3 attempts were actually made.
        assert client.client.models.generate_content.call_count == 3

    @patch("time.sleep")
    def test_non_retryable_error_raises_immediately(self, _mock_sleep):
        """
        A permanent error (e.g. InvalidArgument / PermissionDenied) is NOT
        retried — GeminiInferenceError is raised after exactly one attempt.
        """
        try:
            from google.api_core.exceptions import InvalidArgument
        except ImportError:
            pytest.skip("google-api-core not installed")

        client = _gemini_client_stub()
        client.client.models.generate_content.side_effect = InvalidArgument("bad request")

        with pytest.raises(GeminiInferenceError) as exc_info:
            client.generate("bad prompt")

        err = exc_info.value
        assert err.retryable is False
        assert err.attempts == 1
        # Non-retryable: only one call should have been made.
        assert client.client.models.generate_content.call_count == 1

    @patch("time.sleep")
    def test_unexpected_exception_wrapped_in_gemini_error(self, _mock_sleep):
        """
        An unexpected exception type (not from google-api-core) is still
        wrapped in GeminiInferenceError rather than propagating raw.
        """
        client = _gemini_client_stub()
        client.client.models.generate_content.side_effect = RuntimeError("unexpected")

        with pytest.raises(GeminiInferenceError) as exc_info:
            client.generate("prompt")

        assert "unexpected" in str(exc_info.value)


# =============================================================================
# HTTP status codes from registered exception handlers
# =============================================================================

class TestHTTPErrorResponses:
    """Verify each custom exception maps to the correct HTTP status and body."""

    def test_gemini_inference_error_returns_502(self, test_client):
        """GeminiInferenceError → 502 with error_code GEMINI_INFERENCE_ERROR."""
        # Patch the whole class so __init__ (which creates GeminiClient and
        # tries to authenticate) is never called.
        mock_pipeline = MagicMock()
        mock_pipeline.get_department_summary.side_effect = GeminiInferenceError(
            "Vertex AI unavailable",
            model="gemini-2.0-flash",
            retryable=True,
            attempts=3,
        )
        with patch(
            "src.api.routers.reasoning.RealtimePipeline",
            return_value=mock_pipeline,
        ):
            resp = test_client.post(
                "/api/v1/reasoning/department-summary",
                headers={"X-User-Identity": "alice"},
            )

        assert resp.status_code == 502
        body = resp.json()
        assert body["error_code"] == "GEMINI_INFERENCE_ERROR"
        assert "correlation_id" in body
        assert body["detail"]["retryable"] is True
        assert body["detail"]["attempts"] == 3

    def test_vector_search_error_returns_502(self, test_client):
        """VectorSearchError → 502 with error_code VECTOR_SEARCH_ERROR."""
        with patch(
            "src.api.routers.search.VectorSearch.search_employees",
            side_effect=VectorSearchError(
                "Embeddings not generated",
                table="employees",
                query_preview="senior engineer",
                embeddings_missing=True,
            ),
        ):
            resp = test_client.post(
                "/api/v1/search/employees",
                json={"query": "senior engineer", "top_k": 5},
                headers={"X-User-Identity": "alice"},
            )

        assert resp.status_code == 502
        body = resp.json()
        assert body["error_code"] == "VECTOR_SEARCH_ERROR"
        assert body["detail"]["embeddings_missing"] is True
        assert "correlation_id" in body

    def test_rls_violation_error_returns_500(self, test_client):
        """RLSViolationError → 500 with error_code RLS_VIOLATION_ERROR."""
        with patch(
            "src.api.routers.security.SecureQueryExecutor.query",
            side_effect=RLSViolationError(
                "SET app.active_user failed",
                username="alice",
                operation="set",
            ),
        ):
            resp = test_client.get(
                "/api/v1/security/my-view",
                headers={"X-User-Identity": "alice"},
            )

        assert resp.status_code == 500
        body = resp.json()
        assert body["error_code"] == "RLS_VIOLATION_ERROR"
        assert "correlation_id" in body

    def test_database_connection_error_returns_503(self, test_client):
        """DatabaseConnectionError → 503 with error_code DATABASE_CONNECTION_ERROR."""
        with patch(
            "src.api.routers.sustainability.SecureQueryExecutor.query",
            side_effect=DatabaseConnectionError(
                "Pool exhausted",
                host="10.0.0.2",
                db_name="hr_platform",
            ),
        ):
            resp = test_client.get(
                "/api/v1/sustainability/metrics",
                headers={"X-User-Identity": "alice"},
            )

        assert resp.status_code == 503
        body = resp.json()
        assert body["error_code"] == "DATABASE_CONNECTION_ERROR"
        assert "correlation_id" in body

    def test_correlation_id_present_in_all_error_responses(self, test_client):
        """Every error response body includes a correlation_id field."""
        # Case 1: GeminiInferenceError — patch the whole pipeline class
        # so its __init__ (which creates GeminiClient + authenticates) is skipped.
        mock_pipeline = MagicMock()
        mock_pipeline.get_department_summary.side_effect = GeminiInferenceError("down")
        with patch("src.api.routers.reasoning.RealtimePipeline", return_value=mock_pipeline):
            resp = test_client.post(
                "/api/v1/reasoning/department-summary",
                headers={"X-User-Identity": "alice"},
            )
        assert "correlation_id" in resp.json(), (
            "correlation_id missing from /reasoning/department-summary error response"
        )

        # Case 2: VectorSearchError — patch only the method (VectorSearch.__init__
        # just stores the engine, no network calls).
        with patch(
            "src.api.routers.search.VectorSearch.search_employees",
            side_effect=VectorSearchError("missing embeddings"),
        ):
            resp = test_client.post(
                "/api/v1/search/employees",
                json={"query": "test", "top_k": 5},
                headers={"X-User-Identity": "alice"},
            )
        assert "correlation_id" in resp.json(), (
            "correlation_id missing from /search/employees error response"
        )

    def test_unknown_identity_returns_401_not_500(self, test_client):
        """
        An unknown X-User-Identity header returns 401 via the dependency,
        not 500 from the exception handler fallback.
        """
        resp = test_client.post(
            "/api/v1/reasoning/department-summary",
            headers={"X-User-Identity": "unknown_hacker"},
        )
        assert resp.status_code == 401


# =============================================================================
# VectorSearchError — missing embedding column
# =============================================================================

class TestVectorSearchError:
    def test_raises_on_missing_embedding_column(self):
        """
        search_employees() raises VectorSearchError with embeddings_missing=True
        when the DB raises ProgrammingError about a missing column.
        """
        from src.vector_engine.vector_search import VectorSearch

        mock_engine = MagicMock(name="engine")
        vs = VectorSearch(engine=mock_engine)

        # Simulate a pg8000 ProgrammingError wrapped by SQLAlchemy.
        pg_error = sqlalchemy.exc.ProgrammingError(
            statement="SELECT ...",
            params={},
            orig=Exception('column "embedding" does not exist'),
        )

        with patch(
            "src.vector_engine.vector_search.SecureConnection.__enter__",
            return_value=MagicMock(execute=MagicMock(side_effect=pg_error)),
        ), patch(
            "src.vector_engine.vector_search.SecureConnection.__exit__",
            return_value=False,
        ):
            with pytest.raises(VectorSearchError) as exc_info:
                vs.search_employees("cloud engineer")

        err = exc_info.value
        assert err.embeddings_missing is True
        assert "seed_data.sql" in str(err)

    def test_raises_on_operational_error(self):
        """
        search_employees() wraps sqlalchemy.exc.OperationalError (connection
        drop / timeout) in VectorSearchError without embeddings_missing.
        """
        from src.vector_engine.vector_search import VectorSearch

        mock_engine = MagicMock(name="engine")
        vs = VectorSearch(engine=mock_engine)

        op_error = sqlalchemy.exc.OperationalError(
            statement="SELECT ...", params={}, orig=Exception("connection refused")
        )

        with patch(
            "src.vector_engine.vector_search.SecureConnection.__enter__",
            return_value=MagicMock(execute=MagicMock(side_effect=op_error)),
        ), patch(
            "src.vector_engine.vector_search.SecureConnection.__exit__",
            return_value=False,
        ):
            with pytest.raises(VectorSearchError) as exc_info:
                vs.search_employees("python developer")

        assert exc_info.value.embeddings_missing is False
        assert "employees" in exc_info.value.context.get("table", "")


# =============================================================================
# RLSViolationError — context switch failures
# =============================================================================

class TestRLSViolationError:
    def test_set_user_context_raises_on_operational_error(self):
        """
        set_user_context raises RLSViolationError when the SET command hits a
        connection drop (OperationalError).
        """
        from src.security.context_switcher import set_user_context

        mock_conn = MagicMock()
        mock_conn.execute.side_effect = sqlalchemy.exc.OperationalError(
            statement="SET app.active_user = :u",
            params={"u": "alice"},
            orig=Exception("server closed connection"),
        )

        with pytest.raises(RLSViolationError) as exc_info:
            set_user_context(mock_conn, "alice")

        err = exc_info.value
        assert err.operation == "set"
        assert err.username == "alice"

    def test_set_user_context_raises_on_interface_error(self):
        """set_user_context wraps InterfaceError in RLSViolationError."""
        from src.security.context_switcher import set_user_context

        mock_conn = MagicMock()
        mock_conn.execute.side_effect = sqlalchemy.exc.InterfaceError(
            statement="SET app.active_user = :u",
            params={},
            orig=Exception("broken pipe"),
        )

        with pytest.raises(RLSViolationError) as exc_info:
            set_user_context(mock_conn, "bob")

        assert exc_info.value.operation == "set"

    def test_clear_user_context_raises_on_operational_error(self):
        """
        clear_user_context raises RLSViolationError when the connection drops
        during the SET app.active_user = '' call.
        """
        from src.security.context_switcher import clear_user_context

        mock_conn = MagicMock()
        mock_conn.execute.side_effect = sqlalchemy.exc.OperationalError(
            statement="SET app.active_user = ''",
            params={},
            orig=Exception("connection timed out"),
        )

        with pytest.raises(RLSViolationError) as exc_info:
            clear_user_context(mock_conn)

        err = exc_info.value
        assert err.operation == "clear"

    def test_set_user_context_rejects_empty_username(self):
        """
        set_user_context raises ValueError (not RLSViolationError) for an
        empty username — this is a programming error, not a connection failure.
        """
        from src.security.context_switcher import set_user_context

        mock_conn = MagicMock()
        with pytest.raises(ValueError, match="security violation"):
            set_user_context(mock_conn, "")

        # The connection should never have been touched.
        mock_conn.execute.assert_not_called()
