"""Import data/job_details.json → SQLite."""

import json
import sqlite3
import time

from .lookup  import Lookup
from .parsers import parse_salary, parse_experience, parse_deadline
from .paths   import DB_PATH, JSON_PATH
from .schema  import apply_schema


JOB_COLS = [
    "link_job", "company_id",
    "title", "location", "work_location", "work_time", "work_type",
    "level", "quantity",  "application_method",
    "job_description", "requirements", "benefits",
    "salary_raw", "salary_min", "salary_max",
    "experience_raw", "experience_years",
    "deadline_raw", "deadline",
    "crawled_at",
]
INSERT_JOB_SQL = (
    f"INSERT OR IGNORE INTO jobs ({', '.join(JOB_COLS)}) "
    f"VALUES ({', '.join('?' * len(JOB_COLS))})"
)
INSERT_FTS_SQL = (
    "INSERT INTO jobs_fts "
    "(rowid, title, job_description, requirements, benefits, company_name) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)


# ----- helpers --------------------------------------------------------

def _load_records(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def _build_job_values(rec, company_id):
    s_min, s_max = parse_salary(rec.get("salary"))
    return (
        rec.get("link_job"), company_id,
        rec.get("title"), rec.get("location"),
        rec.get("work_location"), rec.get("work_time"), rec.get("work_type"),
        rec.get("level"), rec.get("quantity"),
        rec.get("application_method"),
        rec.get("job_description"), rec.get("requirements"), rec.get("benefits"),
        rec.get("salary"), s_min, s_max,
        rec.get("experience"), parse_experience(rec.get("experience")),
        rec.get("deadline"),   parse_deadline(rec.get("deadline")),
        rec.get("crawled_at"),
    )


def _insert_fts(cur, job_id, rec):
    cur.execute(INSERT_FTS_SQL, (
        job_id,
        rec.get("title"),
        rec.get("job_description"),
        rec.get("requirements"),
        rec.get("benefits"),
        rec.get("company_name"),
    ))


def _insert_junctions(cur, lookup, job_id, rec):
    for ph in (rec.get("xa_phuong") or []):
        ph = (ph or "").strip()
        if ph:
            cur.execute(
                "INSERT OR IGNORE INTO job_phuong (job_id, phuong_id) VALUES (?, ?)",
                (job_id, lookup.get_phuong(ph)),
            )
    for lj in (rec.get("loai_job") or []):
        lj = (lj or "").strip()
        if lj:
            cur.execute(
                "INSERT OR IGNORE INTO job_loai_jobs (job_id, loai_id) VALUES (?, ?)",
                (job_id, lookup.get_loai(lj)),
            )


def _process_record(cur, lookup, rec, stats):
    """Xử lý 1 record. Return True nếu chèn mới, False nếu skip duplicate."""
    company_id = lookup.get_company(
        rec.get("company_name"),
        rec.get("company_size"),
        rec.get("company_field"),
        rec.get("company_address"),
    )
    cur.execute(INSERT_JOB_SQL, _build_job_values(rec, company_id))
    if cur.rowcount == 0:
        stats["skipped"] += 1
        return False

    job_id = cur.lastrowid
    _insert_fts(cur, job_id, rec)
    _insert_junctions(cur, lookup, job_id, rec)
    stats["inserted"] += 1
    return True


def _print_summary(conn, stats, n_total, elapsed):
    def n(sql):
        return conn.execute(sql).fetchone()[0]

    print()
    print(f"[DONE] Time: {elapsed:.1f}s")
    print(f"  Records processed   : {n_total:,}")
    print(f"  Newly inserted      : {stats['inserted']:,}")
    print(f"  Skipped (dup PK)    : {stats['skipped']:,}")
    print()
    print(f"  jobs                : {n('SELECT COUNT(*) FROM jobs'):,}")
    print(f"  companies           : {n('SELECT COUNT(*) FROM companies'):,}")
    print(f"  phuongs             : {n('SELECT COUNT(*) FROM phuongs'):,}")
    print(f"  loai_jobs           : {n('SELECT COUNT(*) FROM loai_jobs'):,}")
    print(f"  job_phuong          : {n('SELECT COUNT(*) FROM job_phuong'):,}  (junction)")
    print(f"  job_loai_jobs       : {n('SELECT COUNT(*) FROM job_loai_jobs'):,}  (junction)")
    print(f"  jobs_fts            : {n('SELECT COUNT(*) FROM jobs_fts'):,}")
    print(f"  DB                  : {DB_PATH}")


# ----- entry point ---------------------------------------------------

def main():
    data = _load_records(JSON_PATH)

    conn = sqlite3.connect(DB_PATH)
    apply_schema(conn)
    print(f"[INFO] Schema ready @ {DB_PATH}")

    lookup = Lookup(conn)
    cur    = conn.cursor()
    stats  = {"inserted": 0, "skipped": 0}
    t0     = time.time()

    for i, rec in enumerate(data, 1):
        _process_record(cur, lookup, rec, stats)
        if i % 1000 == 0:
            conn.commit()
            print(f"  ... {i:,}/{len(data):,} | inserted={stats['inserted']:,} skipped={stats['skipped']:,}")

    conn.commit()
    _print_summary(conn, stats, len(data), time.time() - t0)
    conn.close()
