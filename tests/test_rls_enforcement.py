"""
Tests for Row-Level Security enforcement.
Verifies that the same query returns different results per user identity.

Requires a running AlloyDB instance with schema + seed data + RLS policies.
Skip with: pytest -m "not integration"
"""

import pytest
from src.config import get_engine
from src.security.secure_query import SecureQueryExecutor
from src.security.context_switcher import set_user_context, get_user_context


@pytest.fixture(scope="module")
def executor():
    try:
        engine = get_engine()
        # Quick connectivity check
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return SecureQueryExecutor(engine)
    except Exception:
        pytest.skip("AlloyDB not available — skipping integration tests")


EMPLOYEE_QUERY = "SELECT id, name, department FROM employees ORDER BY id;"


class TestRLSEnforcement:
    """Verify that RLS policies correctly filter data per user role."""

    def test_admin_sees_all(self, executor):
        rows = executor.query(EMPLOYEE_QUERY, user="eve")
        assert len(rows) >= 20, f"Admin should see all employees, got {len(rows)}"

    def test_manager_sees_own_department(self, executor):
        rows = executor.query(EMPLOYEE_QUERY, user="carol")
        departments = {r["department"] for r in rows}
        assert departments == {"Engineering"}, (
            f"Engineering manager should only see Engineering, got {departments}"
        )

    def test_employee_sees_only_self(self, executor):
        rows = executor.query(EMPLOYEE_QUERY, user="alice")
        assert len(rows) == 1, f"Employee should see 1 row (self), got {len(rows)}"
        assert "alice" in rows[0]["name"].lower()

    def test_different_managers_different_data(self, executor):
        eng_rows = executor.query(EMPLOYEE_QUERY, user="carol")
        mkt_rows = executor.query(EMPLOYEE_QUERY, user="dave")

        eng_names = {r["name"] for r in eng_rows}
        mkt_names = {r["name"] for r in mkt_rows}

        assert eng_names.isdisjoint(mkt_names), (
            "Engineering and Marketing managers should see different employees"
        )

    def test_salary_hidden_from_employees(self, executor):
        rows = executor.query(
            "SELECT * FROM salary_bands ORDER BY id;", user="alice"
        )
        assert len(rows) == 0, "Employees should not see salary bands"

    def test_salary_visible_to_managers(self, executor):
        rows = executor.query(
            "SELECT * FROM salary_bands ORDER BY id;", user="carol"
        )
        assert len(rows) > 0, "Managers should see salary bands"

    def test_compare_access_returns_all_users(self, executor):
        result = executor.compare_access(
            EMPLOYEE_QUERY, ["eve", "carol", "alice"]
        )
        assert len(result) == 3
        assert len(result["eve"]) > len(result["carol"]) > len(result["alice"])


class TestContextSwitcher:
    """Verify session variable management."""

    def test_set_and_get_context(self, executor):
        with executor.engine.connect() as conn:
            set_user_context(conn, "testuser")
            ctx = get_user_context(conn)
            assert ctx == "testuser"

    def test_empty_username_raises(self, executor):
        with executor.engine.connect() as conn:
            with pytest.raises(ValueError, match="security violation"):
                set_user_context(conn, "")

    def test_sanitization(self, executor):
        with executor.engine.connect() as conn:
            set_user_context(conn, "user; DROP TABLE--")
            ctx = get_user_context(conn)
            assert ctx == "userDROPTABLE"
