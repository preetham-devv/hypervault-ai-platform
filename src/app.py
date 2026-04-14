"""
HyperVault AI Platform — Streamlit Dashboard

All data fetching goes through the FastAPI layer (src/api/main.py) via httpx.
The dashboard never imports service classes or touches AlloyDB directly — it
sends HTTP requests with the X-User-Identity header and renders the responses.

Architecture:
  Streamlit (:8501) → httpx → FastAPI (:8080) → AlloyDB / Vertex AI
"""

import logging

import httpx
import pandas as pd
import streamlit as st

from src.config import Config

logging.basicConfig(level=Config.LOG_LEVEL)
logger = logging.getLogger(__name__)

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="HyperVault AI Platform",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar: Identity Switcher ────────────────────────────────────────────────
st.sidebar.title("🔐 Identity Switcher")
st.sidebar.caption("Select a user to see how RLS filters data")

# Demo users — must match VALID_USERS in src/api/dependencies.py.
USERS = {
    "eve":   {"role": "admin",    "dept": "All",         "desc": "Sees everything"},
    "carol": {"role": "manager",  "dept": "Engineering", "desc": "Sees Engineering dept"},
    "dave":  {"role": "manager",  "dept": "Marketing",   "desc": "Sees Marketing dept"},
    "alice": {"role": "employee", "dept": "Engineering", "desc": "Sees only own records"},
    "bob":   {"role": "employee", "dept": "Marketing",   "desc": "Sees only own records"},
}

active_user = st.sidebar.selectbox(
    "Logged in as:",
    list(USERS.keys()),
    format_func=lambda u: f"{u} ({USERS[u]['role']} — {USERS[u]['dept']})",
)

user_info = USERS[active_user]
st.sidebar.info(
    f"**{active_user.title()}**\n\n"
    f"Role: `{user_info['role']}`\n\n"
    f"Department: `{user_info['dept']}`\n\n"
    f"{user_info['desc']}"
)

st.sidebar.divider()
st.sidebar.caption(f"Project: `{Config.PROJECT_ID}`")
st.sidebar.caption(f"Region: `{Config.LOCATION}`")
st.sidebar.caption(f"Model: `{Config.VERTEX_MODEL}`")
st.sidebar.caption(f"API: `{Config.API_BASE_URL}`")

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🧠 HyperVault AI Platform")
st.caption(
    "Real-time reasoning with Gemini · 1M+ vector embeddings · "
    "Zero Trust row-level security"
)


# ── HTTP client ───────────────────────────────────────────────────────────────

@st.cache_resource
def get_api_client() -> httpx.Client:
    """
    Create and cache a single httpx.Client for the Streamlit session.

    ``@st.cache_resource`` means the client (and its underlying connection pool)
    is reused across reruns, avoiding a new TCP handshake on every button click.
    Timeout of 120s covers Gemini reasoning calls which can take several seconds.
    """
    return httpx.Client(
        base_url=Config.API_BASE_URL,
        timeout=httpx.Timeout(120.0, connect=10.0),
    )


def _headers() -> dict[str, str]:
    """Return the identity header for the currently selected user."""
    return {"X-User-Identity": active_user}


def _api(method: str, path: str, **kwargs) -> dict:
    """
    Make an API call and return the parsed JSON response.

    Centralises error handling so every button handler is a simple one-liner.
    Raises ``st.error`` + ``st.stop`` on any non-2xx response so the user sees
    a clear message rather than a Python traceback.
    """
    client = get_api_client()
    try:
        resp = client.request(method, path, headers=_headers(), **kwargs)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.json().get("detail", exc.response.text)
        st.error(f"API error {exc.response.status_code}: {detail}")
        st.stop()
    except httpx.RequestError as exc:
        st.error(
            f"Could not reach the API at `{Config.API_BASE_URL}`. "
            f"Is the FastAPI server running?\n\n`{exc}`"
        )
        st.stop()


# Verify the API is reachable before rendering any tabs.
try:
    _health = get_api_client().get("/health", timeout=5.0)
    _health.raise_for_status()
except Exception as exc:
    st.error(
        f"FastAPI backend is not reachable at `{Config.API_BASE_URL}/health`.\n\n"
        f"Start it with: `uvicorn src.api.main:app --port 8080`\n\n`{exc}`"
    )
    st.stop()


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_reason, tab_search, tab_security, tab_sustain = st.tabs([
    "🤖 AI Reasoning",
    "🔍 Semantic Search",
    "🛡️ Security Demo",
    "🌿 Sustainability",
])


# ── Tab 1: AI Reasoning ───────────────────────────────────────────────────────
with tab_reason:
    st.header("AI-Powered Data Analysis")
    st.write(
        "Queries run through AlloyDB → results sent to Gemini for "
        "real-time reasoning. RLS filters data before the AI sees it."
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📊 Department Summary", use_container_width=True):
            with st.spinner("Querying AlloyDB + Gemini..."):
                result = _api("POST", "/api/v1/reasoning/department-summary")
            st.metric("Rows visible to you", result["row_count"])
            if result["raw_data"]:
                st.dataframe(pd.DataFrame(result["raw_data"]), use_container_width=True)
            st.subheader("AI Insight")
            st.write(result["insight"])

    with col2:
        if st.button("👥 Employee Insights", use_container_width=True):
            with st.spinner("Analyzing performance data..."):
                result = _api("POST", "/api/v1/reasoning/employee-insights")
            st.metric("Rows visible to you", result["row_count"])
            if result["raw_data"]:
                st.dataframe(pd.DataFrame(result["raw_data"]), use_container_width=True)
            st.subheader("AI Insight")
            st.write(result["insight"])

    st.divider()

    st.subheader("Custom Query + AI Analysis")
    custom_sql = st.text_area(
        "SQL Query",
        value="SELECT name, department, salary, role FROM employees ORDER BY salary DESC;",
        height=100,
    )
    custom_question = st.text_input(
        "Question for the AI",
        value="What patterns do you see in compensation across departments?",
    )
    if st.button("Run Analysis"):
        with st.spinner("Processing..."):
            result = _api(
                "POST",
                "/api/v1/reasoning/custom",
                json={"sql": custom_sql, "question": custom_question},
            )
        st.metric("Rows returned", result["row_count"])
        if result["raw_data"]:
            st.dataframe(pd.DataFrame(result["raw_data"]), use_container_width=True)
        st.subheader("AI Insight")
        st.write(result["insight"])


# ── Tab 2: Semantic Search ────────────────────────────────────────────────────
with tab_search:
    st.header("Vector Similarity Search")
    st.write(
        "Embeddings generated by AlloyDB's `google_ml.embedding()` in batch "
        "(zero loops). Search uses IVFFlat ANN index for sub-50ms latency."
    )

    search_query = st.text_input(
        "Search query",
        placeholder="e.g. senior engineer with cloud experience",
    )
    search_type = st.radio(
        "Search in", ["Employees", "Performance Reviews"], horizontal=True
    )
    top_k = st.slider("Results", 5, 25, 10)

    if search_query:
        endpoint = (
            "/api/v1/search/employees"
            if search_type == "Employees"
            else "/api/v1/search/reviews"
        )
        with st.spinner("Searching vectors..."):
            result = _api("POST", endpoint, json={"query": search_query, "top_k": top_k})

        rows = result.get("results", [])
        if rows:
            st.success(f"Found {result['count']} results")
            df = pd.DataFrame(rows)
            if "similarity" in df.columns:
                df["similarity"] = df["similarity"].round(4)
            st.dataframe(df, use_container_width=True)
        else:
            st.warning("No results — embeddings may not be generated yet.")


# ── Tab 3: Security Demo ──────────────────────────────────────────────────────
with tab_security:
    st.header("Zero Trust RLS Demo")
    st.write(
        "The **same SQL query** returns different rows depending on who is "
        "logged in. Security is enforced at the database layer — the AI "
        "never sees unauthorized data."
    )

    demo_sql = "SELECT id, name, department, role, salary FROM employees ORDER BY id;"
    st.code(demo_sql, language="sql")

    if st.button("Run as ALL users to compare"):
        with st.spinner("Querying as each user..."):
            result = _api(
                "GET",
                "/api/v1/security/compare-access",
                params={"sql": demo_sql},
            )

        comparison = result.get("comparison", {})
        for user, rows in comparison.items():
            info = USERS.get(user, {})
            role = info.get("role", "unknown")
            with st.expander(
                f"**{user}** ({role}) — {len(rows)} rows visible",
                expanded=(user == active_user),
            ):
                if rows:
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)
                else:
                    st.info("No rows visible to this user")

    st.divider()
    st.subheader(f"Your view (as `{active_user}`)")
    my_view = _api("GET", "/api/v1/security/my-view", params={"sql": demo_sql})
    if my_view:
        st.metric("Rows you can see", my_view["row_count"])
        if my_view["rows"]:
            st.dataframe(pd.DataFrame(my_view["rows"]), use_container_width=True)


# ── Tab 4: Sustainability ─────────────────────────────────────────────────────
with tab_sustain:
    st.header("ESG / Sustainability Insights")

    metrics_result = _api("GET", "/api/v1/sustainability/metrics")
    metrics_rows = metrics_result.get("metrics", []) if metrics_result else []

    if metrics_rows:
        st.dataframe(pd.DataFrame(metrics_rows), use_container_width=True)

        if st.button("🌿 Generate AI Carbon Analysis"):
            with st.spinner("Gemini analyzing sustainability data..."):
                analysis_result = _api(
                    "POST",
                    "/api/v1/sustainability/analyze",
                    json={"metrics": metrics_rows},
                )
            if analysis_result:
                st.write(analysis_result["analysis"])
    else:
        st.info("No sustainability data found. Run `seed_data.sql` first.")
