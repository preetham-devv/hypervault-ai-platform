# HyperVault AI Platform

**Production-grade AI platform that pushes inference, vector search, and security down to the database layer.**

Most AI applications pull data out of the database, send it to a model externally, and enforce access control in application code. HyperVault eliminates all three hops — Gemini runs inside AlloyDB via `google_ml.predict()`, embeddings are generated in batch SQL with zero Python loops, and Row-Level Security ensures the AI physically cannot access data it shouldn't see.

---

## The Problem

Traditional AI application architecture:

```
App pulls ALL data → Sends to external model → Gets response → Filters by user in app code
```

This creates three risks: **data exfiltration** (sensitive data leaves the database), **latency** (network round trips for every inference), and **security gaps** (one missing IF statement leaks salary data to an intern).

## The Solution

HyperVault moves everything into the database:

```
User query → AlloyDB (RLS filters rows) → google_ml.predict() runs inside DB → Response
```

Data never leaves. Security is enforced by the database engine, not application logic.

---

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│                    Streamlit Frontend                      │
│             (Identity Switcher + AI Dashboard)             │
└──────────┬───────────────┬───────────────┬────────────────┘
           │               │               │
    ┌──────▼───────┐ ┌─────▼───────┐ ┌─────▼───────┐
    │  Reasoning   │ │   Vector    │ │  Security   │
    │   Engine     │ │   Engine    │ │   Layer     │
    │  (Gemini)    │ │ (1M Embed)  │ │   (RLS)     │
    └──────┬───────┘ └─────┬───────┘ └─────┬───────┘
           │               │               │
    ┌──────▼───────────────▼───────────────▼────────────────┐
    │                AlloyDB (PostgreSQL 15)                  │
    │           + Vertex AI Integration Layer                 │
    │     google_ml.predict()  |  google_ml.embedding()      │
    │           + Row-Level Security Policies                 │
    └────────────────────────┬──────────────────────────────┘
                             │
    ┌────────────────────────▼──────────────────────────────┐
    │               Vertex AI (Gemini Flash)                 │
    │          Model Serving + Embedding Generation          │
    └───────────────────────────────────────────────────────┘
```

---

## Features

### Reasoning Engine
Queries AlloyDB data and sends results to Gemini for real-time analysis. Supports two modes:
- **SDK mode** — query data, format as context, call Gemini via Vertex AI SDK
- **In-database mode** — `google_ml.predict()` runs Gemini *inside* AlloyDB. Data never leaves the database.

### Hyperdrive Vector Engine
Generates embeddings for 1M+ rows using a single `UPDATE` statement with `google_ml.embedding()`. AlloyDB's columnar engine parallelizes the work natively. No Python loops, no cursors, no row-by-row API calls. IVFFlat ANN indexes provide sub-50ms similarity search.

### Zero Trust Security (Private Vault)
PostgreSQL Row-Level Security policies enforce data boundaries at the database engine level:
- **Admin** runs `SELECT * FROM employees` → sees 30 rows
- **Manager** runs the same query → sees only their department (8 rows)
- **Employee** runs the same query → sees only their own record (1 row)

Same SQL. Different identity. Different results. The database decides, not the application.

### Sustainability Analytics
ESG/carbon footprint analysis module with Gemini-powered insights — tracks emissions, energy consumption, and waste across departments with automated report generation.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Database | Google Cloud AlloyDB (PostgreSQL 15) |
| AI / LLM | Vertex AI, Gemini Flash |
| Embeddings | `text-embedding-005` via `google_ml.embedding()` |
| Vector Index | IVFFlat (pgvector) |
| Security | PostgreSQL Row-Level Security |
| Frontend | Streamlit |
| Deployment | Cloud Run, Cloud Build |
| Infrastructure | Shell scripts (Terraform planned) |
| Language | Python 3.11 |

---

## Project Structure

```
hypervault-ai-platform/
│
├── src/
│   ├── app.py                              # Streamlit dashboard (4 tabs)
│   ├── config.py                           # DB connection factory + env config
│   │
│   ├── reasoning_engine/
│   │   ├── gemini_client.py                # Vertex AI Gemini client + in-DB SQL
│   │   ├── realtime_pipeline.py            # AlloyDB → Gemini → Insights pipeline
│   │   └── sustainability_analyzer.py      # ESG analysis module
│   │
│   ├── vector_engine/
│   │   ├── batch_embeddings.sql            # Zero-loop 1M embedding generation
│   │   ├── vector_search.py                # Cosine similarity search
│   │   └── benchmark.py                    # p50/p95/p99 latency benchmarks
│   │
│   └── security/
│       ├── rls_policies.sql                # CREATE POLICY definitions
│       ├── context_switcher.py             # Session variable management
│       └── secure_query.py                 # RLS-aware query execution
│
├── infra/
│   ├── setup_vpc.sh                        # VPC + Private Services Access
│   ├── setup_alloydb.sh                    # Cluster + instance provisioning
│   ├── create_tables.sql                   # Schema (employees, reviews, salary)
│   ├── seed_data.sql                       # 30 employees, 16 reviews, ESG data
│   └── cleanup.sh                          # Resource teardown
│
├── deploy/
│   ├── Dockerfile                          # Production container
│   ├── cloudbuild.yaml                     # CI/CD pipeline
│   └── deploy_cloudrun.sh                  # One-command deployment
│
├── tests/
│   ├── test_rls_enforcement.py             # RLS boundary verification
│   ├── test_vector_perf.py                 # Embedding + search tests
│   └── test_reasoning.py                   # Gemini client unit tests (mocked)
│
├── .env.example
├── .gitignore
├── requirements.txt
└── LICENSE
```

---

## Getting Started

### Prerequisites

- Google Cloud account with billing enabled
- Python 3.11+
- `gcloud` CLI installed and authenticated
- APIs enabled: `alloydb.googleapis.com`, `aiplatform.googleapis.com`, `compute.googleapis.com`, `run.googleapis.com`, `servicenetworking.googleapis.com`

### 1. Clone and Configure

```bash
git clone https://github.com/preetham-devv/hypervault-ai-platform.git
cd hypervault-ai-platform

cp .env.example .env
# Fill in: GOOGLE_CLOUD_PROJECT, ALLOYDB_PASSWORD, ALLOYDB_REGION
```

### 2. Provision Infrastructure

```bash
gcloud auth login
gcloud auth application-default login

chmod +x infra/*.sh
./infra/setup_vpc.sh        # VPC + Private Services Access
./infra/setup_alloydb.sh    # AlloyDB cluster + instance + Vertex AI integration
```

After setup, update `ALLOYDB_IP` in `.env` with the IP printed by the script.

### 3. Initialize Database

```bash
psql -h $ALLOYDB_IP -U postgres -d hr_platform -f infra/create_tables.sql
psql -h $ALLOYDB_IP -U postgres -d hr_platform -f infra/seed_data.sql
psql -h $ALLOYDB_IP -U postgres -d hr_platform -f src/security/rls_policies.sql
psql -h $ALLOYDB_IP -U postgres -d hr_platform -f src/vector_engine/batch_embeddings.sql
```

### 4. Run Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run src/app.py
```

### 5. Deploy to Cloud Run

```bash
chmod +x deploy/deploy_cloudrun.sh
./deploy/deploy_cloudrun.sh
```

---

## How RLS Works

The security model uses three components:

**1. Identity table** — `user_roles` maps usernames to roles and departments

**2. Session variable** — on every connection, the app sets:
```sql
SET app.active_user = 'alice';
```

**3. Policies** — PostgreSQL evaluates policies on every query:
```sql
CREATE POLICY employee_self ON employees
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM user_roles
            WHERE username = current_setting('app.active_user', TRUE)
            AND role = 'employee'
            AND LOWER(employees.name) LIKE '%' || LOWER(username) || '%'
        )
    );
```

The AI model, Streamlit app, or any client that connects — none of them can bypass this. The database engine enforces it.

---

## How Batch Embeddings Work

Traditional approach (slow):
```python
for row in rows:           # 1M iterations
    embedding = api.call() # 1M API calls
    db.update(row, embedding)
```

HyperVault approach (fast):
```sql
UPDATE employees
SET embedding = google_ml.embedding(
    model_id => 'text-embedding-005',
    content  => CONCAT(name, '. ', department, '. ', role)
)::vector
WHERE embedding IS NULL;
```

One SQL statement. AlloyDB handles parallelism. Zero application code.

---

## Performance

| Operation | Scale | Latency | Method |
|---|---|---|---|
| Embedding Generation | 1,000,000 rows | ~45 min | Batch SQL (zero loops) |
| Vector Similarity Search | Top-10 from 1M | < 50ms | IVFFlat ANN index |
| Gemini Reasoning | Single query | < 2s | `google_ml.predict()` |
| RLS Policy Enforcement | Per-query overhead | < 1ms | Native PostgreSQL |

---

## Running Tests

```bash
# Unit tests (no GCP required — uses mocked Gemini responses)
pytest tests/test_reasoning.py -v

# Integration tests (requires running AlloyDB)
pytest tests/test_rls_enforcement.py tests/test_vector_perf.py -v
```

---

## Cleanup

To avoid billing charges:

```bash
chmod +x infra/cleanup.sh
./infra/cleanup.sh
```

---

## Roadmap

- [ ] Terraform IaC (replace shell scripts)
- [ ] FastAPI backend layer between frontend and database
- [ ] Connection pool safety for RLS session variables
- [ ] Structured logging with OpenTelemetry + Cloud Trace
- [ ] Docker Compose for local development
- [ ] Pre-commit hooks (ruff, mypy)

---

## License

MIT — see [LICENSE](LICENSE)

## Author

**Sasi Preetham Chopparapu**

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-blue?style=flat&logo=linkedin)](https://www.linkedin.com/in/sasi-preetham-chopparapu/)
[![GitHub](https://img.shields.io/badge/GitHub-Follow-black?style=flat&logo=github)](https://github.com/preetham-devv)
