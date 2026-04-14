-- ============================================================
-- The Private Vault: Zero Trust Intelligence with RLS
-- ============================================================
-- The database physically refuses to return unauthorized rows,
-- regardless of what the AI agent queries.
-- ============================================================

-- Identity provider table
CREATE TABLE IF NOT EXISTS user_roles (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(100) UNIQUE NOT NULL,
    role        VARCHAR(50) NOT NULL CHECK (role IN ('admin','manager','employee')),
    department  VARCHAR(100),
    created_at  TIMESTAMP DEFAULT NOW()
);

INSERT INTO user_roles (username, role, department) VALUES
    ('alice',   'employee', 'Engineering'),
    ('bob',     'employee', 'Marketing'),
    ('carol',   'manager',  'Engineering'),
    ('dave',    'manager',  'Marketing'),
    ('eve',     'admin',    NULL)
ON CONFLICT (username) DO NOTHING;

-- Enable and FORCE RLS (even for table owners)
ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE employees FORCE ROW LEVEL SECURITY;
ALTER TABLE performance_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE performance_reviews FORCE ROW LEVEL SECURITY;
ALTER TABLE salary_bands ENABLE ROW LEVEL SECURITY;
ALTER TABLE salary_bands FORCE ROW LEVEL SECURITY;

-- ── EMPLOYEES ──
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

-- ── PERFORMANCE REVIEWS ──
CREATE POLICY admin_rev ON performance_reviews FOR ALL USING (
    EXISTS (SELECT 1 FROM user_roles
            WHERE username = current_setting('app.active_user', TRUE)
            AND role = 'admin')
);

CREATE POLICY mgr_rev ON performance_reviews FOR SELECT USING (
    EXISTS (SELECT 1 FROM user_roles ur
            JOIN employees e ON e.id = performance_reviews.employee_id
            WHERE ur.username = current_setting('app.active_user', TRUE)
            AND ur.role = 'manager' AND ur.department = e.department)
);

CREATE POLICY self_rev ON performance_reviews FOR SELECT USING (
    EXISTS (SELECT 1 FROM user_roles ur
            JOIN employees e ON e.id = performance_reviews.employee_id
            WHERE ur.username = current_setting('app.active_user', TRUE)
            AND ur.role = 'employee'
            AND LOWER(e.name) LIKE '%' || LOWER(ur.username) || '%')
);

-- ── SALARY BANDS ── (admin + manager only)
CREATE POLICY admin_mgr_salary ON salary_bands FOR ALL USING (
    EXISTS (SELECT 1 FROM user_roles
            WHERE username = current_setting('app.active_user', TRUE)
            AND role IN ('admin','manager'))
);
