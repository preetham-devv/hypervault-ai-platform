-- ============================================================
-- Hyperdrive: 1M+ Embeddings, Zero Loops
-- ============================================================
-- AlloyDB's google_ml.embedding() runs batch embedding generation
-- entirely inside the database engine. No Python loops, no
-- row-by-row API calls, no application-layer bottlenecks.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS google_ml_integration CASCADE;
CREATE EXTENSION IF NOT EXISTS vector;

-- Register the embedding model
CALL google_ml.create_model(
    model_id             => 'text-embedding-005',
    model_type           => 'text_embedding',
    model_qualified_name => 'text-embedding-005',
    model_provider       => 'google'
);

-- Add embedding columns
ALTER TABLE employees
    ADD COLUMN IF NOT EXISTS embedding vector(768);
ALTER TABLE performance_reviews
    ADD COLUMN IF NOT EXISTS embedding vector(768);

-- ============================================================
-- THE HYPERDRIVE — single UPDATE, parallel processing, zero loops
-- ============================================================

-- Employees: embed composite text
UPDATE employees
SET embedding = google_ml.embedding(
    model_id => 'text-embedding-005',
    content  => CONCAT(
        'Employee: ', name,
        '. Department: ', department,
        '. Role: ', role,
        '. Skills: ', COALESCE(skills, 'not specified')
    )
)::vector
WHERE embedding IS NULL;

-- Reviews: embed review text
UPDATE performance_reviews
SET embedding = google_ml.embedding(
    model_id => 'text-embedding-005',
    content  => CONCAT(
        'Review for employee ', employee_id,
        '. Rating: ', rating, '/5. ',
        review_text
    )
)::vector
WHERE embedding IS NULL;

-- ANN indexes for sub-linear similarity search
CREATE INDEX IF NOT EXISTS idx_emp_embedding
    ON employees USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_rev_embedding
    ON performance_reviews USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Verify coverage
SELECT 'employees' AS tbl, COUNT(*) AS total,
       COUNT(embedding) AS embedded,
       ROUND(100.0 * COUNT(embedding) / NULLIF(COUNT(*),0), 2) AS pct
FROM employees
UNION ALL
SELECT 'performance_reviews', COUNT(*), COUNT(embedding),
       ROUND(100.0 * COUNT(embedding) / NULLIF(COUNT(*),0), 2)
FROM performance_reviews;
