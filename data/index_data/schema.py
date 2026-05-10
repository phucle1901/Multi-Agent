"""Schema DDL: 5 bảng + indexes + FTS5."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS phuongs (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS loai_jobs (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS companies (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT    NOT NULL UNIQUE,
    size    TEXT,
    field   TEXT,
    address TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    link_job           TEXT    NOT NULL UNIQUE,
    company_id         INTEGER REFERENCES companies(id),

    title              TEXT,
    location           TEXT,
    work_location      TEXT,
    work_time          TEXT,
    work_type          TEXT,
    level              TEXT,
    quantity           TEXT,
    application_method TEXT,

    job_description    TEXT,
    requirements       TEXT,
    benefits           TEXT,

    salary_raw         TEXT,
    salary_min         REAL,
    salary_max         REAL,

    experience_raw     TEXT,
    experience_years   REAL,

    deadline_raw       TEXT,
    deadline           DATE,

    crawled_at         TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_phuong (
    job_id    INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    phuong_id INTEGER NOT NULL REFERENCES phuongs(id),
    PRIMARY KEY (job_id, phuong_id)
);

CREATE TABLE IF NOT EXISTS job_loai_jobs (
    job_id  INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    loai_id INTEGER NOT NULL REFERENCES loai_jobs(id),
    PRIMARY KEY (job_id, loai_id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_salary_min  ON jobs(salary_min);
CREATE INDEX IF NOT EXISTS idx_jobs_salary_max  ON jobs(salary_max);
CREATE INDEX IF NOT EXISTS idx_jobs_deadline    ON jobs(deadline);
CREATE INDEX IF NOT EXISTS idx_jobs_company     ON jobs(company_id);
CREATE INDEX IF NOT EXISTS idx_jobs_level       ON jobs(level);
CREATE INDEX IF NOT EXISTS idx_jobs_experience  ON jobs(experience_years);
CREATE INDEX IF NOT EXISTS idx_jp_phuong        ON job_phuong(phuong_id);
CREATE INDEX IF NOT EXISTS idx_jl_loai          ON job_loai_jobs(loai_id);

CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts USING fts5(
    title, job_description, requirements, benefits, company_name,
    tokenize="unicode61 remove_diacritics 2"
);
"""


def apply_schema(conn):
    """Tạo toàn bộ bảng/index/FTS nếu chưa có."""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
