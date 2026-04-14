-- ============================================================
-- Sample HR Dataset — 30 employees across 4 departments
-- ============================================================

INSERT INTO employees (name, email, department, role, salary, hire_date, skills) VALUES
('Alice Chen',       'alice@company.com',     'Engineering',  'Senior SWE',           145000, '2021-03-15', 'Python, GCP, Kubernetes, AlloyDB'),
('Bob Martinez',     'bob@company.com',       'Marketing',    'Content Strategist',    92000, '2022-06-01', 'SEO, Analytics, Copywriting'),
('Carol Williams',   'carol@company.com',     'Engineering',  'Engineering Manager',  175000, '2019-11-20', 'Java, Architecture, Team Leadership'),
('Dave Thompson',    'dave@company.com',       'Marketing',    'Marketing Manager',    160000, '2020-01-10', 'Growth, Branding, Budget Management'),
('Eve Johnson',      'eve@company.com',        'Engineering',  'VP of Engineering',    220000, '2018-05-01', 'Strategy, Cloud Architecture, AI/ML'),
('Frank Lee',        'frank@company.com',      'Engineering',  'ML Engineer',          155000, '2022-01-15', 'TensorFlow, Vertex AI, Python'),
('Grace Kim',        'grace@company.com',      'Sales',        'Account Executive',    105000, '2021-09-01', 'Enterprise Sales, CRM, Negotiation'),
('Henry Patel',      'henry@company.com',      'Engineering',  'DevOps Engineer',      140000, '2022-03-20', 'Terraform, GCP, CI/CD, Docker'),
('Iris Rodriguez',   'iris@company.com',       'HR',           'HR Director',          165000, '2019-07-01', 'Talent Acquisition, Compliance, D&I'),
('Jack Wilson',      'jack@company.com',       'Sales',        'Sales Manager',        150000, '2020-04-15', 'Team Leadership, Pipeline, Forecasting'),
('Karen Davis',      'karen@company.com',      'Engineering',  'Frontend Engineer',    130000, '2023-01-10', 'React, TypeScript, Figma'),
('Leo Garcia',       'leo@company.com',        'Marketing',    'Growth Analyst',        88000, '2023-06-01', 'SQL, Python, A/B Testing'),
('Mia Brown',        'mia@company.com',        'HR',           'Recruiter',             85000, '2023-02-15', 'Sourcing, Interviewing, ATS'),
('Noah Taylor',      'noah@company.com',       'Engineering',  'Backend Engineer',     135000, '2022-08-01', 'Java, Spring Boot, PostgreSQL, Kafka'),
('Olivia White',     'olivia@company.com',     'Sales',        'SDR',                   72000, '2024-01-15', 'Outreach, Salesforce, Cold Calling'),
('Peter Nguyen',     'peter@company.com',      'Engineering',  'Data Engineer',        142000, '2021-11-01', 'BigQuery, Spark, Airflow, dbt'),
('Quinn Adams',      'quinn@company.com',      'Marketing',    'Design Lead',          120000, '2021-04-01', 'Figma, Brand Design, Motion Graphics'),
('Rachel Scott',     'rachel@company.com',     'Engineering',  'SRE',                  148000, '2022-05-15', 'GCP, Monitoring, Incident Response'),
('Sam Mitchell',     'sam@company.com',        'HR',           'Compensation Analyst',  95000, '2023-09-01', 'Excel, Benchmarking, Pay Equity'),
('Tina Cooper',      'tina@company.com',       'Sales',        'Enterprise AE',        125000, '2021-07-01', 'Fortune 500, Contracts, Demos'),
('Uma Reddy',        'uma@company.com',        'Engineering',  'Platform Engineer',    150000, '2022-10-01', 'Kubernetes, Istio, AlloyDB, Spanner'),
('Victor Zhao',      'victor@company.com',     'Engineering',  'Staff Engineer',       185000, '2019-03-01', 'System Design, Mentoring, Go, Rust'),
('Wendy Park',       'wendy@company.com',      'Marketing',    'PMM',                  115000, '2022-12-01', 'Positioning, Launch, Competitive Intel'),
('Xavier Moore',     'xavier@company.com',     'Engineering',  'Security Engineer',    155000, '2021-06-15', 'IAM, Zero Trust, Pen Testing'),
('Yara Singh',       'yara@company.com',       'HR',           'L&D Manager',          110000, '2020-08-01', 'Training, Career Dev, LMS'),
('Zach Turner',      'zach@company.com',       'Sales',        'Sales Ops',             98000, '2023-03-15', 'Salesforce, Reporting, Forecasting'),
('Amy Foster',       'amy@company.com',        'Engineering',  'Junior SWE',            95000, '2024-06-01', 'Python, SQL, Git'),
('Brian Hayes',      'brian@company.com',      'Marketing',    'Social Media Mgr',      82000, '2023-11-01', 'Instagram, TikTok, Analytics'),
('Cindy Bell',       'cindy@company.com',      'Engineering',  'QA Lead',              125000, '2021-02-01', 'Selenium, Pytest, CI/CD, JIRA'),
('Derek Long',       'derek@company.com',      'Sales',        'VP of Sales',          200000, '2018-09-01', 'Strategy, P&L, Executive Relationships');

-- Performance reviews
INSERT INTO performance_reviews (employee_id, reviewer_id, rating, review_text, review_date, review_period, goals_met) VALUES
(1,  3, 5, 'Alice consistently exceeds expectations. Led the AlloyDB migration ahead of schedule. Excellent mentoring of junior engineers.',               '2025-01-15', '2024-H2', TRUE),
(1,  3, 4, 'Strong technical contribution. Could improve on cross-team communication.',                                                                    '2024-07-10', '2024-H1', TRUE),
(2,  4, 3, 'Bob delivers solid content but needs to improve on data-driven decision making. SEO metrics show moderate improvement.',                        '2025-01-20', '2024-H2', FALSE),
(3,  5, 5, 'Carol is an exceptional engineering manager. Team velocity up 40% under her leadership. Zero attrition in her org.',                            '2025-01-18', '2024-H2', TRUE),
(4,  5, 4, 'Dave drove a successful rebrand campaign. ROI exceeded targets by 15%. Needs to better manage agency relationships.',                           '2025-01-22', '2024-H2', TRUE),
(6,  3, 4, 'Frank built a production ML pipeline that reduced inference latency by 60%. Needs to document his work more thoroughly.',                       '2025-01-16', '2024-H2', TRUE),
(7, 10, 3, 'Grace hit 85% of quota. Strong relationship building but struggles with closing large enterprise deals.',                                       '2025-02-01', '2024-H2', FALSE),
(8,  3, 5, 'Henry automated the entire deployment pipeline. Reduced deploy times from 45 min to 3 min. Exceptional reliability focus.',                     '2025-01-17', '2024-H2', TRUE),
(9,  5, 4, 'Iris led the compensation review and implemented a new pay equity framework. Effective but could move faster on policy changes.',               '2025-01-25', '2024-H2', TRUE),
(11, 3, 3, 'Karen shows promise in frontend development but needs more experience with production systems. Good code quality.',                             '2025-01-19', '2024-H2', FALSE),
(14, 3, 4, 'Noah is a reliable backend engineer. Delivered the payment service refactor on time. Could take on more technical leadership.',                  '2025-01-20', '2024-H2', TRUE),
(16, 3, 5, 'Peter owns the data platform end-to-end. BigQuery costs reduced 40% through his optimization work. Excellent systems thinking.',               '2025-01-21', '2024-H2', TRUE),
(18, 3, 4, 'Rachel has excellent incident response skills. Led 12 incident reviews with actionable outcomes. Could mentor more junior SREs.',               '2025-01-22', '2024-H2', TRUE),
(21, 3, 4, 'Uma drove the Spanner migration for the billing platform. Solid execution, good cross-team collaboration.',                                     '2025-01-23', '2024-H2', TRUE),
(22, 5, 5, 'Victor is a force multiplier. His architecture reviews have prevented multiple production issues. A true staff-level contributor.',             '2025-01-24', '2024-H2', TRUE),
(24, 3, 4, 'Xavier improved our security posture significantly. Completed SOC2 audit with zero critical findings.',                                         '2025-01-25', '2024-H2', TRUE);

-- Salary bands
INSERT INTO salary_bands (department, role_level, min_salary, max_salary) VALUES
('Engineering', 'Junior',   85000,  110000),
('Engineering', 'Mid',     120000,  150000),
('Engineering', 'Senior',  140000,  180000),
('Engineering', 'Staff',   170000,  210000),
('Engineering', 'Manager', 160000,  200000),
('Marketing',   'Junior',   65000,   85000),
('Marketing',   'Mid',      85000,  120000),
('Marketing',   'Senior',  110000,  145000),
('Marketing',   'Manager', 140000,  180000),
('Sales',       'SDR',      60000,   80000),
('Sales',       'AE',       90000,  130000),
('Sales',       'Manager', 135000,  175000),
('Sales',       'VP',      180000,  240000),
('HR',          'Junior',   70000,   90000),
('HR',          'Mid',      90000,  120000),
('HR',          'Senior',  110000,  150000),
('HR',          'Director',150000,  190000);

-- Sustainability metrics
INSERT INTO sustainability_metrics (department, quarter, carbon_kg, energy_kwh, waste_kg, renewable_pct) VALUES
('Engineering', '2024-Q1', 12500, 85000, 320, 42.5),
('Engineering', '2024-Q2', 11800, 82000, 290, 48.0),
('Engineering', '2024-Q3', 10200, 78000, 250, 55.2),
('Engineering', '2024-Q4',  9500, 74000, 210, 62.0),
('Marketing',   '2024-Q1',  4200, 28000, 180, 35.0),
('Marketing',   '2024-Q2',  3900, 26000, 160, 40.5),
('Marketing',   '2024-Q3',  3600, 24500, 140, 46.0),
('Marketing',   '2024-Q4',  3300, 23000, 120, 52.0),
('Sales',       '2024-Q1',  6800, 45000, 250, 30.0),
('Sales',       '2024-Q2',  6500, 43000, 230, 34.0),
('Sales',       '2024-Q3',  6100, 41000, 200, 38.5),
('Sales',       '2024-Q4',  5700, 39000, 180, 43.0),
('HR',          '2024-Q1',  2100, 14000,  90, 50.0),
('HR',          '2024-Q2',  1900, 13000,  80, 55.0),
('HR',          '2024-Q3',  1750, 12000,  70, 60.0),
('HR',          '2024-Q4',  1600, 11000,  60, 65.0);
