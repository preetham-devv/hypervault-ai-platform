-- ============================================================
-- AlloyDB AI Platform — Core Schema
-- ============================================================

CREATE EXTENSION IF NOT EXISTS google_ml_integration CASCADE;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS employees (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    email       VARCHAR(200) UNIQUE NOT NULL,
    department  VARCHAR(100) NOT NULL,
    role        VARCHAR(150) NOT NULL,
    salary      NUMERIC(12,2) NOT NULL,
    hire_date   DATE NOT NULL DEFAULT CURRENT_DATE,
    manager_id  INTEGER REFERENCES employees(id),
    skills      TEXT,
    location    VARCHAR(100) DEFAULT 'Atlanta, GA',
    status      VARCHAR(20) DEFAULT 'active'
                CHECK (status IN ('active','inactive','on_leave')),
    embedding   vector(768),
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS performance_reviews (
    id            SERIAL PRIMARY KEY,
    employee_id   INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    reviewer_id   INTEGER REFERENCES employees(id),
    rating        INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_text   TEXT NOT NULL,
    review_date   DATE NOT NULL DEFAULT CURRENT_DATE,
    review_period VARCHAR(20) NOT NULL,
    goals_met     BOOLEAN DEFAULT FALSE,
    embedding     vector(768),
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS salary_bands (
    id          SERIAL PRIMARY KEY,
    department  VARCHAR(100) NOT NULL,
    role_level  VARCHAR(50) NOT NULL,
    min_salary  NUMERIC(12,2) NOT NULL,
    max_salary  NUMERIC(12,2) NOT NULL,
    currency    VARCHAR(3) DEFAULT 'USD',
    effective   DATE DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS sustainability_metrics (
    id              SERIAL PRIMARY KEY,
    department      VARCHAR(100) NOT NULL,
    quarter         VARCHAR(10) NOT NULL,
    carbon_kg       NUMERIC(12,2),
    energy_kwh      NUMERIC(12,2),
    waste_kg        NUMERIC(12,2),
    renewable_pct   NUMERIC(5,2),
    recorded_at     TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_emp_dept ON employees(department);
CREATE INDEX IF NOT EXISTS idx_emp_status ON employees(status);
CREATE INDEX IF NOT EXISTS idx_rev_emp ON performance_reviews(employee_id);
CREATE INDEX IF NOT EXISTS idx_rev_date ON performance_reviews(review_date DESC);
