-- =============================================================
-- Multi-Agent · Data Layer Schema (SQLite)
-- Spec: docs/design_data.md
-- =============================================================

-- ---- Nhóm 1 · User & Runtime ----

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT UNIQUE NOT NULL,
    name        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mode        TEXT NOT NULL CHECK(mode IN
                ('mode_0','mode_1','mode_2','mode_3','mode_4','mode_5','mode_6')),
    title       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_conv_user_updated ON conversations(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
    content         TEXT NOT NULL,
    metadata        TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_msg_conv_created
    ON messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_msg_conv_handler_created
    ON messages(conversation_id, json_extract(metadata, '$.handled_by'), created_at DESC);

CREATE TABLE IF NOT EXISTS user_profile (
    user_id                INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    current_role           TEXT,
    years_experience       INTEGER,
    skills                 TEXT NOT NULL DEFAULT '[]',
    goal_type              TEXT CHECK(goal_type IS NULL OR goal_type IN
                           ('career_change','promotion','first_job',
                            'skill_acquisition','salary_increase','exploring')),
    target_role            TEXT,
    target_salary_min_vnd  INTEGER,
    target_salary_max_vnd  INTEGER,
    mbti_type              TEXT CHECK(mbti_type IS NULL OR length(mbti_type)=4),
    holland_code           TEXT CHECK(holland_code IS NULL OR length(holland_code)=3),
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS memory_facts (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                 INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category                TEXT NOT NULL CHECK(category IN ('preference','style')),
    content                 TEXT NOT NULL,
    source_conversation_id  INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
    source_message_id       INTEGER REFERENCES messages(id) ON DELETE SET NULL,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_mem_user_cat_updated
    ON memory_facts(user_id, category, updated_at DESC);

-- ---- Nhóm 2 · Jobs & Companies ----

CREATE TABLE IF NOT EXISTS companies (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT UNIQUE NOT NULL,
    size_raw      TEXT,
    field_raw     TEXT,
    address       TEXT,
    size_bucket   TEXT CHECK(size_bucket IS NULL OR size_bucket IN
                  ('startup','sme','large_corp'))
);
CREATE INDEX IF NOT EXISTS idx_companies_field       ON companies(field_raw);
CREATE INDEX IF NOT EXISTS idx_companies_size_bucket ON companies(size_bucket);

CREATE TABLE IF NOT EXISTS phuongs (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS loai_jobs (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    source                  TEXT NOT NULL DEFAULT 'topcv',
    link_job                TEXT UNIQUE NOT NULL,
    company_id              INTEGER REFERENCES companies(id),

    title                   TEXT NOT NULL,
    location_raw            TEXT,
    work_location           TEXT,
    work_time               TEXT,
    work_type               TEXT CHECK(work_type IS NULL OR work_type IN
                            ('Toàn thời gian','Bán thời gian','Thực tập',
                             'Khác','Làm tại nhà','Thời vụ')),
    level_raw               TEXT,
    quantity                TEXT,
    application_method      TEXT,
    job_description         TEXT,
    requirements            TEXT,
    benefits                TEXT,
    salary_raw              TEXT,
    experience_raw          TEXT,
    deadline_raw            TEXT,

    salary_min              INTEGER,
    salary_max              INTEGER,
    experience_years        REAL,
    deadline                TEXT,

    work_mode_extracted     TEXT CHECK(work_mode_extracted IS NULL OR work_mode_extracted IN
                            ('remote','hybrid','onsite','unknown')),
    work_mode_extracted_at  TEXT,
    skills_extracted_at     TEXT,

    crawled_at              TEXT NOT NULL,
    imported_at             TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_jobs_company           ON jobs(company_id);
CREATE INDEX IF NOT EXISTS idx_jobs_salary_min        ON jobs(salary_min);
CREATE INDEX IF NOT EXISTS idx_jobs_salary_max        ON jobs(salary_max);
CREATE INDEX IF NOT EXISTS idx_jobs_deadline          ON jobs(deadline);
CREATE INDEX IF NOT EXISTS idx_jobs_exp               ON jobs(experience_years);
CREATE INDEX IF NOT EXISTS idx_jobs_work_mode         ON jobs(work_mode_extracted);
CREATE INDEX IF NOT EXISTS idx_jobs_work_type         ON jobs(work_type);
CREATE INDEX IF NOT EXISTS idx_jobs_skills_extracted  ON jobs(skills_extracted_at);
CREATE INDEX IF NOT EXISTS idx_jobs_wm_extracted      ON jobs(work_mode_extracted_at);

CREATE TABLE IF NOT EXISTS job_phuong (
    job_id     INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    phuong_id  INTEGER NOT NULL REFERENCES phuongs(id),
    PRIMARY KEY (job_id, phuong_id)
);
CREATE INDEX IF NOT EXISTS idx_job_phuong_phuong ON job_phuong(phuong_id);

CREATE TABLE IF NOT EXISTS job_loai_jobs (
    job_id   INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    loai_id  INTEGER NOT NULL REFERENCES loai_jobs(id),
    PRIMARY KEY (job_id, loai_id)
);
CREATE INDEX IF NOT EXISTS idx_job_loai_loai ON job_loai_jobs(loai_id);

CREATE TABLE IF NOT EXISTS job_skills (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    skill_name  TEXT NOT NULL,
    category    TEXT NOT NULL CHECK(category IN ('hard','soft','tool','certificate')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(job_id, skill_name, category)
);
CREATE INDEX IF NOT EXISTS idx_job_skills_job  ON job_skills(job_id);
CREATE INDEX IF NOT EXISTS idx_job_skills_name ON job_skills(skill_name);

-- ---- FTS5 (search theo title, bỏ dấu tiếng Việt) ----

CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts USING fts5(
    title,
    content='jobs',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS jobs_ai AFTER INSERT ON jobs BEGIN
    INSERT INTO jobs_fts(rowid, title) VALUES (new.id, new.title);
END;

CREATE TRIGGER IF NOT EXISTS jobs_ad AFTER DELETE ON jobs BEGIN
    INSERT INTO jobs_fts(jobs_fts, rowid, title) VALUES('delete', old.id, old.title);
END;

CREATE TRIGGER IF NOT EXISTS jobs_au AFTER UPDATE OF title ON jobs BEGIN
    INSERT INTO jobs_fts(jobs_fts, rowid, title) VALUES('delete', old.id, old.title);
    INSERT INTO jobs_fts(rowid, title) VALUES (new.id, new.title);
END;
