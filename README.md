# AlloyDB AI Platform

**Production-Grade AI Architecture with AlloyDB, Gemini, and Zero Trust Security**

An end-to-end AI-powered HR analytics platform built on Google Cloud AlloyDB. The system performs real-time reasoning with Gemini Flash, processes 1M+ vector embeddings using AlloyDB's native parallel operations (zero Python loops), and enforces row-level security so AI agents never leak data across user boundaries.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   Streamlit Frontend                      │
│            (Identity Switcher + AI Dashboard)             │
└──────────┬──────────────┬──────────────┬─────────────────┘
           │              │              │
    ┌──────▼──────┐ ┌─────▼──────┐ ┌────▼───────┐
    │  Reasoning  │ │   Vector   │ │  Security  │
    │   Engine    │ │   Engine   │ │   Layer    │
    │  (Gemini)   │ │ (1M Embed) │ │   (RLS)    │
    └──────┬──────┘ └─────┬──────┘ └────┬───────┘
           │              │              │
    ┌──────▼──────────────▼──────────────▼─────────────────┐
    │               AlloyDB (PostgreSQL 15)                  │
    │          + Vertex AI Integration Layer                  │
    │    google_ml.predict()  |  google_ml.embedding()       │
    │          + Row-Level Security Policies                  │
    └──────────────────────────────────────────────────────┘
```

## Key Features

- **Real-Time Reasoning Engine** — Queries AlloyDB and passes results to Gemini for instant analysis via `google_ml.predict()` directly inside SQL
- **Hyperdrive Vector Engine** — Generates embeddings for 1M+ rows using `google_ml.embedding()` in batch SQL with zero application-layer loops
- **Zero Trust Security (Private Vault)** — PostgreSQL RLS policies enforce data boundaries at the database layer. AI agents physically cannot access unauthorized rows
- **Identity-Aware AI** — Same query returns different results depending on who is logged in

## Prerequisites

- Google Cloud account with billing enabled
- Python 3.11+
- `gcloud` CLI installed and configured
- APIs enabled: AlloyDB, Vertex AI, Compute Engine, Cloud Run

## Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/alloydb-ai-platform.git
cd alloydb-ai-platform

cp .env.example .env
# Edit .env with your GCP project details

# Infrastructure
gcloud auth login && gcloud auth application-default login
chmod +x infra/*.sh
./infra/setup_vpc.sh
./infra/setup_alloydb.sh

# Database
psql -h $ALLOYDB_IP -U postgres -d hr_platform -f infra/create_tables.sql
psql -h $ALLOYDB_IP -U postgres -d hr_platform -f infra/seed_data.sql
psql -h $ALLOYDB_IP -U postgres -d hr_platform -f src/security/rls_policies.sql
psql -h $ALLOYDB_IP -U postgres -d hr_platform -f src/vector_engine/batch_embeddings.sql

# Run
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run src/app.py
```

## Performance Benchmarks

| Operation | Scale | Latency | Method |
|---|---|---|---|
| Embedding Generation | 1,000,000 rows | ~45 min | Batch SQL (zero loops) |
| Vector Similarity Search | Top-10 from 1M | < 50ms | IVFFlat ANN index |
| Gemini Reasoning | Single query | < 2s | google_ml.predict() |
| RLS Enforcement | Per-query overhead | < 1ms | Native PostgreSQL |

## Security Model

1. No application-level filtering — the database refuses unauthorized rows
2. Session-based identity — each connection sets `app.active_user` as a PostgreSQL session variable
3. Policy-driven access — `CREATE POLICY` checks `user_roles` against the session variable
4. AI boundary enforcement — even `SELECT *` is silently filtered by RLS

## Deploy to Cloud Run

```bash
chmod +x deploy/deploy_cloudrun.sh
./deploy/deploy_cloudrun.sh
```

## License

MIT

## Author

**Sasi Preetham Chopparapu**
