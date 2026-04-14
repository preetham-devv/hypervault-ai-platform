"""
AlloyDB AI Platform — Streamlit Dashboard

Features:
  - Identity Switcher (simulates multi-user login for RLS demo)
  - AI Reasoning tab (Gemini-powered data analysis)
  - Semantic Search tab (vector similarity search)
  - Security Demo tab (shows RLS filtering per user)
  - Sustainability tab (ESG insights)
"""

import streamlit as st
import pandas as pd
import logging

from src.config import get_engine, Config
from src.reasoning_engine.realtime_pipeline import RealtimePipeline
from src.reasoning_engine.sustainability_analyzer import SustainabilityAnalyzer
from src.vector_engine.vector_search import VectorSearch
from src.security.secure_query import SecureQueryExecutor

logging.basicConfig(level=Config.LOG_LEVEL)
logger = logging.getLogger(__name__)

# ── Page Config ──
st.set_page_config(
    page_title="AlloyDB AI Platform",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar: Identity Switcher ──
st.sidebar.title("🔐 Identity Switcher")
st.sidebar.caption("Select a user to see how RLS filters data")

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

# ── Header ──
st.title("🧠 AlloyDB AI Platform")
st.caption(
    "Real-time reasoning with Gemini · 1M+ vector embeddings · "
    "Zero Trust row-level security"
)

# ── Initialize services ──
@st.cache_resource
def init_services():
    engine = get_engine()
    return {
        "pipeline": RealtimePipeline(engine),
        "search": VectorSearch(engine),
        "secure": SecureQueryExecutor(engine),
        "sustainability": SustainabilityAnalyzer(),
    }


try:
    svc = init_services()
except Exception as e:
    st.error(
        f"Could not connect to AlloyDB. Make sure your `.env` is configured "
        f"and the database is running.\n\n`{e}`"
    )
    st.stop()

# ── Tabs ──
tab_reason, tab_search, tab_security, tab_sustain = st.tabs([
    "🤖 AI Reasoning",
    "🔍 Semantic Search",
    "🛡️ Security Demo",
    "🌿 Sustainability",
])

# ── Tab 1: AI Reasoning ──
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
                result = svc["pipeline"].get_department_summary(active_user)
            st.metric("Rows visible to you", result["row_count"])
            if result["raw_data"]:
                st.dataframe(pd.DataFrame(result["raw_data"]), use_container_width=True)
            st.subheader("AI Insight")
            st.write(result["insight"])

    with col2:
        if st.button("👥 Employee Insights", use_container_width=True):
            with st.spinner("Analyzing performance data..."):
                result = svc["pipeline"].get_employee_insights(active_user)
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
            result = svc["pipeline"].query_and_reason(
                custom_sql, custom_question, active_user
            )
        st.metric("Rows returned", result["row_count"])
        if result["raw_data"]:
            st.dataframe(pd.DataFrame(result["raw_data"]), use_container_width=True)
        st.subheader("AI Insight")
        st.write(result["insight"])

# ── Tab 2: Semantic Search ──
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
        with st.spinner("Searching vectors..."):
            if search_type == "Employees":
                results = svc["search"].search_employees(
                    search_query, top_k, active_user
                )
            else:
                results = svc["search"].search_reviews(
                    search_query, top_k, active_user
                )

        if results:
            st.success(f"Found {len(results)} results")
            df = pd.DataFrame(results)
            if "similarity" in df.columns:
                df["similarity"] = df["similarity"].round(4)
            st.dataframe(df, use_container_width=True)
        else:
            st.warning("No results — embeddings may not be generated yet.")

# ── Tab 3: Security Demo ──
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
            comparison = svc["secure"].compare_access(
                demo_sql, list(USERS.keys())
            )

        for user, rows in comparison.items():
            info = USERS[user]
            with st.expander(
                f"**{user}** ({info['role']}) — {len(rows)} rows visible",
                expanded=(user == active_user),
            ):
                if rows:
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)
                else:
                    st.info("No rows visible to this user")

    st.divider()
    st.subheader(f"Your view (as `{active_user}`)")
    your_rows = svc["secure"].query(demo_sql, user=active_user)
    st.metric("Rows you can see", len(your_rows))
    if your_rows:
        st.dataframe(pd.DataFrame(your_rows), use_container_width=True)

# ── Tab 4: Sustainability ──
with tab_sustain:
    st.header("ESG / Sustainability Insights")

    metrics_rows = svc["secure"].query(
        "SELECT * FROM sustainability_metrics ORDER BY quarter, department;",
        user="eve",  # sustainability data visible to all
    )

    if metrics_rows:
        df = pd.DataFrame(metrics_rows)
        st.dataframe(df, use_container_width=True)

        if st.button("🌿 Generate AI Carbon Analysis"):
            with st.spinner("Gemini analyzing sustainability data..."):
                analysis = svc["sustainability"].analyze_carbon_footprint(metrics_rows)
            st.write(analysis)
    else:
        st.info("No sustainability data found. Run `seed_data.sql` first.")
