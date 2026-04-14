FROM python:3.11-slim

WORKDIR /app

# ── System dependencies ───────────────────────────────────────────────────────
# supervisor: process manager that runs FastAPI + Streamlit side-by-side.
# libpq-dev / build-essential: required by pg8000 and psycopg2 C extensions.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ───────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application source ────────────────────────────────────────────────────────
COPY . .

# ── Non-root user ─────────────────────────────────────────────────────────────
# Cloud Run recommends running as non-root. supervisord.conf sets user=appuser.
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# ── Supervisord config ────────────────────────────────────────────────────────
COPY deploy/supervisord.conf /etc/supervisor/conf.d/services.conf

# ── Ports ─────────────────────────────────────────────────────────────────────
# 8080 — FastAPI (Cloud Run ingress port; external traffic arrives here)
# 8501 — Streamlit (internal only; called by the browser via the Cloud Run URL
#         only if you add a path-based load balancer or nginx in front)
EXPOSE 8080 8501

# ── Environment defaults ──────────────────────────────────────────────────────
# Cloud Run injects PORT=8080 automatically; we honour it for FastAPI.
ENV PORT=8080
# Tell Streamlit where the API lives (same container → localhost).
ENV API_BASE_URL=http://localhost:8080
# Streamlit settings — headless prevents the browser-launch prompt.
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# ── Entrypoint ────────────────────────────────────────────────────────────────
# supervisord starts both FastAPI (priority=10) and Streamlit (priority=20).
# If either process crashes, supervisor restarts it automatically (autorestart=true).
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/services.conf"]
