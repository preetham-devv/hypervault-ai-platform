-- ============================================================
-- Local development schema for Docker Compose postgres:15 +
-- pgvector (pgvector/pgvector:pg15 image).
--
-- Differences from the production AlloyDB schema
-- (infra/create_tables.sql + src/security/rls_policies.sql):
--
--   1. google_ml_integration is OMITTED — AlloyDB-only extension.
--      Queries that call google_ml.embedding() or google_ml.predict_row()
--      will fail locally; they require an AlloyDB instance.
--      Vector columns (embedding vector(768)) are retained for schema
--      compatibility; you can INSERT embeddings manually for testing.
--
--   2. A non-superuser `hypervault_app` role is created and granted the
--      minimum privileges needed by the application.  The superuser
--      `postgres` bypasses RLS (PostgreSQL behaviour), so the app must
--      connect as `hypervault_app` to exercise the RLS policies locally.
--
-- Run order in /docker-entrypoint-initdb.d/:
--   01-schema.sql  (this file)  — extensions, tables, user, RLS
--   02-seed.sql                 — sample data (infra/seed_data.sql)
-- ============================================================

-- ── Extensions ────────────────────────────────────────────────────────────────
-- pgvector is pre-installed in the pgvector/pgvector:pg15 Docker image.
CREATE EXTENSION IF NOT EXISTS vector;

-- ── Core tables ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS employees (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(200)  NOT NULL,
    email       VARCHAR(200)  UNIQUE NOT NULL,
    department  VARCHAR(100)  NOT NULL,
    role        VARCHAR(150)  NOT NULL,
    salary      NUMERIC(12,2) NOT NULL,
    hire_date   DATE          NOT NULL DEFAULT CURRENT_DATE,
    manager_id  INTEGER       REFERENCES employees(id),
    skills      TEXT,
    location    VARCHAR(100)  DEFAULT 'Atlanta, GA',
    status      VARCHAR(20)   DEFAULT 'active'
                CHECK (status IN ('active','inactive','on_leave')),
    -- pgvector column: populated by seed scripts or AlloyDB batch embeddings.
    embedding   vector(768),
    created_at  TIMESTAMP     DEFAULT NOW(),
    updated_at  TIMESTAMP     DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS performance_reviews (
    id            SERIAL PRIMARY KEY,
    employee_id   INTEGER       NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    reviewer_id   INTEGER       REFERENCES employees(id),
    rating        INTEGER       NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_text   TEXT          NOT NULL,
    review_date   DATE          NOT NULL DEFAULT CURRENT_DATE,
    review_period VARCHAR(20)   NOT NULL,
    goals_met     BOOLEAN       DEFAULT FALSE,
    embedding     vector(768),
    created_at    TIMESTAMP     DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS salary_bands (
    id          SERIAL PRIMARY KEY,
    department  VARCHAR(100)  NOT NULL,
    role_level  VARCHAR(50)   NOT NULL,
    min_salary  NUMERIC(12,2) NOT NULL,
    max_salary  NUMERIC(12,2) NOT NULL,
    currency    VARCHAR(3)    DEFAULT 'USD',
    effective   DATE          DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS sustainability_metrics (
    id            SERIAL PRIMARY KEY,
    department    VARCHAR(100)  NOT NULL,
    quarter       VARCHAR(10)   NOT NULL,
    carbon_kg     NUMERIC(12,2),
    energy_kwh    NUMERIC(12,2),
    waste_kg      NUMERIC(12,2),
    renewable_pct NUMERIC(5,2),
    recorded_at   TIMESTAMP     DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_emp_dept   ON employees(department);
CREATE INDEX IF NOT EXISTS idx_emp_status ON employees(status);
CREATE INDEX IF NOT EXISTS idx_rev_emp    ON performance_reviews(employee_id);
CREATE INDEX IF NOT EXISTS idx_rev_date   ON performance_reviews(review_date DESC);

-- ── Row-Level Security: identity table ───────────────────────────────────────
-- Mirrors the production definition in src/security/rls_policies.sql.
-- Populated here so RLS policies can look up roles at query time.

CREATE TABLE IF NOT EXISTS user_roles (
    id         SERIAL PRIMARY KEY,
    username   VARCHAR(100) UNIQUE NOT NULL,
    role       VARCHAR(50)  NOT NULL CHECK (role IN ('admin','manager','employee')),
    department VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO user_roles (username, role, department) VALUES
    ('alice', 'employee', 'Engineering'),
    ('bob',   'employee', 'Marketing'),
    ('carol', 'manager',  'Engineering'),
    ('dave',  'manager',  'Marketing'),
    ('eve',   'admin',    NULL)
ON CONFLICT (username) DO NOTHING;

-- ── Row-Level Security: enable & force ───────────────────────────────────────
-- FORCE ROW LEVEL SECURITY prevents the table owner from bypassing policies.
-- The postgres *superuser* still bypasses RLS (PostgreSQL design); the
-- application should connect as hypervault_app to exercise policies locally.

ALTER TABLE employees          ENABLE ROW LEVEL SECURITY;
ALTER TABLE employees          FORCE  ROW LEVEL SECURITY;
ALTER TABLE performance_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE performance_reviews FORCE  ROW LEVEL SECURITY;
ALTER TABLE salary_bands        ENABLE ROW LEVEL SECURITY;
ALTER TABLE salary_bands        FORCE  ROW LEVEL SECURITY;

-- ── RLS policies — employees ─────────────────────────────────────────────────

CREATE POLICY admin_emp ON employees FOR ALL USING (
    EXISTS (SELECT 1 FROM user_roles
            WHERE username = current_setting('app.active_user', TRUE)
              AND role = 'admin')
);

CREATE POLICY mgr_emp ON employees FOR SELECT USING (
    EXISTS (SELECT 1 FROM user_roles
            WHERE username = current_setting('app.active_user', TRUE)
              AND role = 'manager'
              AND user_roles.department = employees.department)
);

CREATE POLICY self_emp ON employees FOR SELECT USING (
    EXISTS (SELECT 1 FROM user_roles
            WHERE username = current_setting('app.active_user', TRUE)
              AND role = 'employee'
              AND LOWER(employees.name) LIKE '%' || LOWER(username) || '%')
);

-- ── RLS policies — performance_reviews ───────────────────────────────────────

CREATE POLICY admin_rev ON performance_reviews FOR ALL USING (
    EXISTS (SELECT 1 FROM user_roles
            WHERE username = current_setting('app.active_user', TRUE)
              AND role = 'admin')
);

CREATE POLICY mgr_rev ON performance_reviews FOR SELECT USING (
    EXISTS (SELECT 1 FROM user_roles ur
            JOIN employees e ON e.id = performance_reviews.employee_id
            WHERE ur.username = current_setting('app.active_user', TRUE)
              AND ur.role = 'manager'
              AND ur.department = e.department)
);

CREATE POLICY self_rev ON performance_reviews FOR SELECT USING (
    EXISTS (SELECT 1 FROM user_roles ur
            JOIN employees e ON e.id = performance_reviews.employee_id
            WHERE ur.username = current_setting('app.active_user', TRUE)
              AND ur.role = 'employee'
              AND LOWER(e.name) LIKE '%' || LOWER(ur.username) || '%')
);

-- ── RLS policies — salary_bands ──────────────────────────────────────────────

CREATE POLICY admin_mgr_salary ON salary_bands FOR ALL USING (
    EXISTS (SELECT 1 FROM user_roles
            WHERE username = current_setting('app.active_user', TRUE)
              AND role IN ('admin','manager'))
);

-- ── Application user ──────────────────────────────────────────────────────────
-- hypervault_app is a non-superuser so RLS policies actually fire.
-- The postgres superuser bypasses RLS unconditionally (PostgreSQL design),
-- which means connecting as postgres masks RLS issues in local development.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'hypervault_app') THEN
        CREATE USER hypervault_app WITH PASSWORD 'localdev_app';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE hr_platform TO hypervault_app;
GRANT USAGE   ON SCHEMA public TO hypervault_app;

-- Data manipulation: app only needs SELECT + INSERT (no schema changes).
GRANT SELECT, INSERT, UPDATE ON ALL TABLES    IN SCHEMA public TO hypervault_app;
GRANT USAGE                  ON ALL SEQUENCES IN SCHEMA public TO hypervault_app;

-- Future tables created by migrations should inherit the same grants.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE ON TABLES    TO hypervault_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE                  ON SEQUENCES TO hypervault_app;
