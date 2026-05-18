"""Pipeline 0 · Bulk import job_details.json → SQL."""
from __future__ import annotations

import json
from collections import Counter

from data.index_data import config
from data.index_data.db import get_conn, init_schema
from data.index_data.parsers import (
    parse_salary, parse_experience, parse_deadline,
    normalize_phuong, normalize_company, derive_size_bucket,
)

REQUIRED = ('link_job', 'title', 'company_name', 'job_description', 'requirements')
ALLOWED_WORK_TYPES = {
    'Toàn thời gian', 'Bán thời gian', 'Thực tập',
    'Khác', 'Làm tại nhà', 'Thời vụ',
}

def dedup_by_link(records):
    """Gộp record trùng link_job: union xa_phuong + loai_job, giữ scalar non-null đầu tiên."""
    by_link = {}
    for r in records:
        link = r.get('link_job')
        if not link:
            continue
        if link not in by_link:
            r2 = dict(r)
            r2['xa_phuong'] = list(r.get('xa_phuong') or [])
            r2['loai_job'] = list(r.get('loai_job') or [])
            by_link[link] = r2
        else:
            cur = by_link[link]
            cur['xa_phuong'] = list(dict.fromkeys(cur['xa_phuong'] + (r.get('xa_phuong') or [])))
            cur['loai_job'] = list(dict.fromkeys(cur['loai_job'] + (r.get('loai_job') or [])))
            for k, v in r.items():
                if k in ('xa_phuong', 'loai_job'):
                    continue
                if cur.get(k) is None and v is not None:
                    cur[k] = v
    return list(by_link.values())

def is_complete(r) -> bool:
    return all(r.get(k) for k in REQUIRED)

def get_or_create(conn, table, cache, name, extra_cols=(), extra_vals=()):
    """Upsert vào bảng có cột UNIQUE 'name'. Cache in-memory để tránh SELECT lặp."""
    if name in cache:
        return cache[name]
    cols = ('name',) + tuple(extra_cols)
    vals = (name,) + tuple(extra_vals)
    placeholders = ','.join('?' * len(cols))
    cur = conn.execute(
        f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) VALUES ({placeholders})",
        vals,
    )
    if cur.rowcount > 0:
        cache[name] = cur.lastrowid
    else:
        row = conn.execute(f"SELECT id FROM {table} WHERE name=?", (name,)).fetchone()
        cache[name] = row['id']
    return cache[name]

def import_jobs(json_path=None, db_path=None):
    json_path = json_path or config.JOB_DETAILS_JSON
    db_path = db_path or config.DB_PATH

    with open(json_path, encoding='utf-8') as f:
        records = json.load(f)
    print(f"Loaded:              {len(records)} record")

    deduped = dedup_by_link(records)
    print(f"Sau dedup:           {len(deduped)} (gộp {len(records) - len(deduped)})")

    complete = [r for r in deduped if is_complete(r)]
    print(f"Đủ field bắt buộc:   {len(complete)} (loại {len(deduped) - len(complete)})")

    conn = get_conn(db_path)
    init_schema(conn)

    co_cache, ph_cache, lj_cache = {}, {}, {}
    stats = Counter()

    conn.execute("BEGIN")
    try:
        for r in complete:
            co_id = get_or_create(
                conn, 'companies', co_cache,
                normalize_company(r['company_name']),
                extra_cols=('size_raw', 'field_raw', 'address', 'size_bucket'),
                extra_vals=(
                    r.get('company_size'),
                    r.get('company_field'),
                    r.get('company_address'),
                    derive_size_bucket(r.get('company_size')),
                ),
            )

            s_min, s_max = parse_salary(r.get('salary'))
            exp_years = parse_experience(r.get('experience'))
            deadline = parse_deadline(r.get('deadline'))
            work_type = r.get('work_type') if r.get('work_type') in ALLOWED_WORK_TYPES else None

            cur = conn.execute(
                """INSERT OR IGNORE INTO jobs (
                    source, link_job, company_id, title,
                    location_raw, work_location, work_time, work_type,
                    level_raw, quantity, application_method,
                    job_description, requirements, benefits,
                    salary_raw, experience_raw, deadline_raw,
                    salary_min, salary_max, experience_years, deadline,
                    crawled_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    'topcv', r['link_job'], co_id, r['title'],
                    r.get('location'), r.get('work_location'),
                    r.get('work_time'), work_type,
                    r.get('level'), r.get('quantity'),
                    r.get('application_method'),
                    r['job_description'], r['requirements'],
                    r.get('benefits'),
                    r.get('salary'), r.get('experience'),
                    r.get('deadline'),
                    s_min, s_max, exp_years, deadline,
                    r['crawled_at'],
                ),
            )
            if cur.rowcount == 0:
                stats['job_skipped'] += 1
                continue
            job_id = cur.lastrowid
            stats['job_inserted'] += 1

            for raw_p in r.get('xa_phuong') or []:
                ph_id = get_or_create(conn, 'phuongs', ph_cache, normalize_phuong(raw_p))
                conn.execute(
                    "INSERT OR IGNORE INTO job_phuong (job_id, phuong_id) VALUES (?, ?)",
                    (job_id, ph_id),
                )

            for raw_l in r.get('loai_job') or []:
                lj_name = (raw_l or '').strip()
                if not lj_name:
                    continue
                lj_id = get_or_create(conn, 'loai_jobs', lj_cache, lj_name)
                conn.execute(
                    "INSERT OR IGNORE INTO job_loai_jobs (job_id, loai_id) VALUES (?, ?)",
                    (job_id, lj_id),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    conn.execute("INSERT INTO jobs_fts(jobs_fts) VALUES('rebuild')")
    conn.commit()

    print()
    print("=== Tổng kết ===")
    print(f"jobs inserted:       {stats['job_inserted']}")
    print(f"jobs skipped (dup):  {stats['job_skipped']}")
    print(f"companies:           {conn.execute('SELECT COUNT(*) FROM companies').fetchone()[0]}")
    print(f"phuongs:             {conn.execute('SELECT COUNT(*) FROM phuongs').fetchone()[0]}")
    print(f"loai_jobs:           {conn.execute('SELECT COUNT(*) FROM loai_jobs').fetchone()[0]}")
    print(f"job_phuong:          {conn.execute('SELECT COUNT(*) FROM job_phuong').fetchone()[0]}")
    print(f"job_loai_jobs:       {conn.execute('SELECT COUNT(*) FROM job_loai_jobs').fetchone()[0]}")
    print(f"jobs_fts (indexed):  {conn.execute('SELECT COUNT(*) FROM jobs_fts').fetchone()[0]}")
    conn.close()

if __name__ == "__main__":
    import_jobs()
