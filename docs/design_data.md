# Design Data

Schema toàn bộ data layer: **SQL (SQLite)** + **Qdrant** + **Static files** + **Pipeline offline**.

---

## 0 · Stack & convention

| Layer | Công nghệ |
|---|---|
| Relational | SQLite (FTS5 built-in) |
| Vector | Qdrant |
| Embedding | OpenAI `text-embedding-3-small` — 1536-D, cosine |
| Static | JSON files trong `data/` |

**Đơn vị & format**:
- Salary: **VND INTEGER** mọi bảng (vd `60_000_000`). `triệu × 1_000_000`, USD × 26,000.
- Date: `YYYY-MM-DD`. Datetime app-controlled: `datetime('now')` (`YYYY-MM-DD HH:MM:SS`, không TZ). Datetime crawl giữ verbatim. **Không mix format trong cùng 1 cột.**
- JSON column: TEXT, query bằng `json_extract(col, '$.path')` (SQLite, không phải `->>`).

**PRAGMA mỗi connection**:
```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -64000;     -- ~64 MB
```

---

## I · SQL — User & Runtime

> Dễ migrate; có thể drop & rebuild bất kỳ lúc nào.

### `users`
```sql
CREATE TABLE users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT UNIQUE NOT NULL,
    name        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
```
Auth fields (password_hash, oauth...) ngoài scope đồ án.

### `conversations`
```sql
CREATE TABLE conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mode        TEXT NOT NULL CHECK(mode IN
                ('mode_0','mode_1','mode_2','mode_3','mode_4','mode_5','mode_6')),
    title       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_conv_user_updated ON conversations(user_id, updated_at DESC);
```

### `messages`
```sql
CREATE TABLE messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
    content         TEXT NOT NULL,
    metadata        TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_msg_conv_created          ON messages(conversation_id, created_at);
CREATE INDEX idx_msg_conv_handler_created  ON messages(
    conversation_id,
    json_extract(metadata, '$.handled_by'),
    created_at DESC
);
```

`metadata` JSON: `{"handled_by": "manager_c", "last_search": {"filter": {...}}}`. Expression index chỉ hit khi query dùng đúng `json_extract(metadata, '$.handled_by')`.

### `user_profile`
1 row : 1 user. Ghi bởi Agent 3 · Profile — **trừ blacklist** (`goal_*`, `mbti_*`, `holland_*`, `*_completed_at`).

```sql
CREATE TABLE user_profile (
    user_id                     INTEGER PRIMARY KEY
                                REFERENCES users(id) ON DELETE CASCADE,

    -- Education
    highest_degree              TEXT CHECK(highest_degree IS NULL OR highest_degree IN
                                ('high_school','college','university','master','phd')),
    major                       TEXT,
    school                      TEXT,
    graduation_year             INTEGER,
    gpa                         REAL,

    -- Experience (current only)
    years_experience            INTEGER,
    current_role                TEXT,
    current_company             TEXT,
    current_salary_vnd_month    INTEGER,
    employment_status           TEXT CHECK(employment_status IS NULL OR employment_status IN
                                ('employed','unemployed','student','freelancer')),

    -- Skills (JSON arrays)
    hard_skills                 TEXT NOT NULL DEFAULT '[]',   -- ["SQL","Python"]
    soft_skills                 TEXT NOT NULL DEFAULT '[]',
    languages                   TEXT NOT NULL DEFAULT '[]',   -- [{"lang":"English","level":"B2"}]
    certificates                TEXT NOT NULL DEFAULT '[]',

    -- Goal (chỉ Agent 4 · Goal Setting set)
    goal_type                   TEXT CHECK(goal_type IS NULL OR goal_type IN
                                ('career_change','promotion','first_job','skill_acquisition')),
    target_role                 TEXT,
    target_salary_min_vnd       INTEGER,
    target_salary_max_vnd       INTEGER,
    target_date                 TEXT,
    target_location             TEXT,                          -- Profile ĐƯỢC ghi (không blacklist)

    -- Assessment (chỉ Agent 5 set)
    mbti_type                   TEXT CHECK(mbti_type IS NULL OR length(mbti_type)=4),
    holland_code                TEXT CHECK(holland_code IS NULL OR length(holland_code)=3),
    mbti_completed_at           TEXT,
    holland_completed_at        TEXT,

    -- Job preferences
    work_mode                   TEXT CHECK(work_mode IS NULL OR work_mode IN
                                ('remote','hybrid','onsite')),
    company_size_pref           TEXT CHECK(company_size_pref IS NULL OR company_size_pref IN
                                ('startup','sme','large_corp')),
    preferred_industries        TEXT NOT NULL DEFAULT '[]',

    created_at                  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at                  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### `memory_facts`
Free-form fact dài hạn, ghi bởi Agent 2 · Memory.

```sql
CREATE TABLE memory_facts (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                 INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category                TEXT NOT NULL CHECK(category IN
                            ('preference','context','emotion','interaction_meta')),
    content                 TEXT NOT NULL,
    source_conversation_id  INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
    source_message_id       INTEGER REFERENCES messages(id) ON DELETE SET NULL,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_mem_user_cat_updated ON memory_facts(user_id, category, updated_at DESC);
```

---

## II · SQL — Jobs & Companies (CRITICAL)

> ⚠️ Bất biến sau khi import. Cột `*_raw` giữ verbatim; cột parsed có thể re-derive.

### `companies`
```sql
CREATE TABLE companies (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT UNIQUE NOT NULL,    -- trim + collapse whitespace, giữ case
    size_raw      TEXT,                    -- "500-1000 nhân viên" / "1000+ nhân viên"
    field_raw     TEXT,                    -- "IT - Phần mềm" / ~41 distinct values
    address       TEXT,                    -- display only
    size_bucket   TEXT CHECK(size_bucket IS NULL OR size_bucket IN
                  ('startup','sme','large_corp'))
);

CREATE INDEX idx_companies_field        ON companies(field_raw);
CREATE INDEX idx_companies_size_bucket  ON companies(size_bucket);
```

**Rule `size_bucket`** (parse lower bound từ `size_raw`): `<25` → `startup`, `25 ≤ x < 500` → `sme`, `≥500` → `large_corp`, no-number / NULL → NULL.

### `phuongs`
```sql
CREATE TABLE phuongs (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT UNIQUE NOT NULL
);
```

**Normalize**: trim + collapse + lowercase prefix `phường`/`xã` + title-case rest (vd `"phường lĩnh nam"` → `"phường Lĩnh Nam"`). Dataset: 124 distinct.

### `loai_jobs`
```sql
CREATE TABLE loai_jobs (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT UNIQUE NOT NULL    -- verbatim từ topcv
);
```

Dataset: 22 distinct, không normalize.

### `jobs` (core)
```sql
CREATE TABLE jobs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    source                  TEXT NOT NULL DEFAULT 'topcv',
    link_job                TEXT UNIQUE NOT NULL,
    company_id              INTEGER REFERENCES companies(id),

    -- Raw từ crawl (verbatim)
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

    -- Parsed (Pipeline 0)
    salary_min              INTEGER,          -- VND/tháng
    salary_max              INTEGER,          -- VND/tháng
    experience_years        REAL,             -- 0.0 = "Không yêu cầu"
    deadline                TEXT,             -- "YYYY-MM-DD"

    -- Offline LLM extract (Pipeline 1, 2)
    work_mode_extracted     TEXT CHECK(work_mode_extracted IS NULL OR work_mode_extracted IN
                            ('remote','hybrid','onsite','unknown')),
    work_mode_extracted_at  TEXT,
    skills_extracted_at     TEXT,

    crawled_at              TEXT NOT NULL,
    imported_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_jobs_company           ON jobs(company_id);
CREATE INDEX idx_jobs_salary_min        ON jobs(salary_min);
CREATE INDEX idx_jobs_salary_max        ON jobs(salary_max);
CREATE INDEX idx_jobs_deadline          ON jobs(deadline);
CREATE INDEX idx_jobs_exp               ON jobs(experience_years);
CREATE INDEX idx_jobs_work_mode         ON jobs(work_mode_extracted);
CREATE INDEX idx_jobs_work_type         ON jobs(work_type);
CREATE INDEX idx_jobs_skills_extracted  ON jobs(skills_extracted_at);
CREATE INDEX idx_jobs_wm_extracted      ON jobs(work_mode_extracted_at);
```

**Note**:
- `level_raw` KHÔNG index filter — Job Search dùng `experience_years` làm proxy.
- Crawl field `gender` 100% NULL → drop.
- Idempotency Pipeline 0 = `INSERT OR IGNORE` strict skip.
- Crawler đã filter Hà Nội từ đầu → coi mọi record là HN, không lưu cờ riêng. Mọi job có `xa_phuong` non-empty đều insert vào `job_phuong`.

**Query Job Search theo phường**:
```sql
EXISTS (SELECT 1 FROM job_phuong WHERE job_id=jobs.id AND phuong_id=?)
```

### `job_phuong` (M:N)
```sql
CREATE TABLE job_phuong (
    job_id     INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    phuong_id  INTEGER NOT NULL REFERENCES phuongs(id),
    PRIMARY KEY (job_id, phuong_id)
);

CREATE INDEX idx_job_phuong_phuong ON job_phuong(phuong_id);
```

### `job_loai_jobs` (M:N)
```sql
CREATE TABLE job_loai_jobs (
    job_id   INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    loai_id  INTEGER NOT NULL REFERENCES loai_jobs(id),
    PRIMARY KEY (job_id, loai_id)
);

CREATE INDEX idx_job_loai_loai ON job_loai_jobs(loai_id);
```

### `job_skills` (Pipeline 1)
```sql
CREATE TABLE job_skills (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    skill_name  TEXT NOT NULL,
    category    TEXT NOT NULL CHECK(category IN ('hard','soft','tool','certificate')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(job_id, skill_name, category)
);

CREATE INDEX idx_job_skills_job  ON job_skills(job_id);
CREATE INDEX idx_job_skills_name ON job_skills(skill_name);
```

`UNIQUE` cho Pipeline 1 re-run idempotent.

### `jobs_fts` (FTS5)
```sql
CREATE VIRTUAL TABLE jobs_fts USING fts5(
    title,
    content='jobs',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER jobs_ai AFTER INSERT ON jobs BEGIN
    INSERT INTO jobs_fts(rowid, title) VALUES (new.id, new.title);
END;

CREATE TRIGGER jobs_ad AFTER DELETE ON jobs BEGIN
    INSERT INTO jobs_fts(jobs_fts, rowid, title) VALUES('delete', old.id, old.title);
END;

CREATE TRIGGER jobs_au AFTER UPDATE OF title ON jobs BEGIN
    INSERT INTO jobs_fts(jobs_fts, rowid, title) VALUES('delete', old.id, old.title);
    INSERT INTO jobs_fts(rowid, title) VALUES (new.id, new.title);
END;
```

Scope = title only. Tokenize bỏ dấu → search `"Cau Giay"` match `"Cầu Giấy"`.

---

## III · Qdrant

```python
VectorParams(size=1536, distance=Distance.COSINE)
```

**Point ID = `jobs.id`** (integer) đồng nhất SQL ↔ Qdrant. 2 collection cùng config vector.

| Collection | Embedding text | Payload | Mục đích |
|---|---|---|---|
| `jobs` | `title \| company \| field_raw \| loai_jobs \| job_description \| requirements \| benefits` (cap 8000 tokens) | `{"job_id": int}` | Semantic full-doc — Job Search rerank |
| `job_titles` | `"{title} \| {level_raw} \| {loai_jobs}"` | `{"job_id": int}` | Title-focused precision — Skill Gap Mode A, Job Search soft match |

KHÔNG include salary/experience/level/work_type trong embedding text (đã filter SQL). Indexed payload: `job_id` only.

**Pattern truy vấn**:
```
SQL hard-filter → list[job_id]
  → Qdrant filter MatchAny(job_id IN ...) → top-K rank
  → SQL re-fetch detail by id
```

Payload chỉ `job_id` → SQL là single source of truth.

**KHÔNG có collection**: `companies` (Agent 10 dùng Tavily), `occupations` (Agent 6 pure LLM), `memory_facts` (Agent 2 chốt không embed).

---

## IV · Static files

```
data/assessments/{mbti,holland}_{questions,interpretations}.json   # Agent 5
data/canonical_skills.json                                          # TODO — Pipeline 1 + Profile
```

`canonical_skills.json` cấu trúc: `[{name, category, aliases[]}]` — dùng làm canonical list cho Pipeline 1 prompt + Profile slot-fill ([prompt-conventions.md:31-44](./prompt-conventions.md#L31-L44)).

---

## V · Pipelines

### Pipeline 0 · Bulk import (1 lần)

**Input** `data/job_details.json` (14,833 records) → **Output** SQL Nhóm 2. Kỳ vọng ~13,500-14,500 rows `jobs`.

1. Load + dedup theo `link_job` (merge `xa_phuong` ∪ `loai_job`, giữ non-null scalar).
2. Reject record thiếu bất kỳ: `link_job`, `title`, `company_name`, `job_description`, `requirements`.
3. Upsert `companies` (normalize name, derive `size_bucket`).
4. Parse `salary_raw`, `experience_raw`, `deadline_raw` (section VI).
5. `INSERT OR IGNORE INTO jobs`. **Nếu `rowcount == 0` → SKIP step 6** (không dùng `lastrowid` cũ).
6. Insert M:N: `job_loai_jobs` cho từng `loai_job` value; `job_phuong` cho từng phường trong `xa_phuong` (normalize trước).
7. FTS5 sync qua trigger; bulk có thể disable trigger rồi `INSERT INTO jobs_fts(jobs_fts) VALUES('rebuild')`.

### Pipeline 1 · Skill extract (LLM)
Trigger `skills_extracted_at IS NULL`. Batch 5-10 jobs/call:
```
text = title + requirements + job_description
LLM → [{skill_name (canonical), category}]
INSERT OR IGNORE INTO job_skills    -- UNIQUE constraint dedup
UPDATE jobs SET skills_extracted_at = datetime('now')
```

### Pipeline 2 · Work mode extract
Trigger `work_mode_extracted_at IS NULL`.
```
text = lower(title + job_description + benefits + work_time + work_location)
REMOTE_KW    = ["remote","wfh","work from home","tại nhà","làm việc tại nhà"]
AMBIGUOUS_KW = ["hybrid","linh hoạt","online","từ xa"]

PHA 1 (no LLM):
  if work_type == "Làm tại nhà" or any(kw in text for kw in REMOTE_KW):  → 'remote'
  elif any(kw in text for kw in AMBIGUOUS_KW):                           → PHA 2
  else:                                                                  → 'onsite'

PHA 2 (LLM): "JD này hybrid (vị trí mix) hay 'linh hoạt' chỉ giờ giấc?"
  → 'hybrid' / 'onsite' / 'unknown'
```

### Pipeline 3 + 4 · Embed → Qdrant
Trigger: jobs chưa có point trong Qdrant collection tương ứng. Batch 200:
```
# Pipeline 3 — collection 'jobs'
text = build_full_doc(job, company, loai_jobs)    # format section III
if tokens(text) > 8000: truncate
qdrant.upsert(collection='jobs', point_id=job.id,
              vector=embed(text), payload={"job_id": job.id})

# Pipeline 4 — collection 'job_titles'
text = f"{title} | {level_raw or ''} | {loai_str}"
qdrant.upsert(collection='job_titles', point_id=job.id,
              vector=embed(text), payload={"job_id": job.id})
```

### Pipeline 5 · Cleanup expired (cron daily)
Xoá point Qdrant cho `jobs.deadline < date('now', '-7 days')` ở cả 2 collection. **KHÔNG** xoá SQL row (giữ history cho Manager D).

**Thứ tự**: Pipeline 0 (blocking) → 1, 2, 3, 4 song song. Pipeline 5 cron riêng.

---

## VI · Parsing rules

### Salary → VND INTEGER

| Pattern | `salary_min` | `salary_max` |
|---|---|---|
| `"X - Y triệu"` | `X × 10⁶` | `Y × 10⁶` |
| `"Từ X triệu"` | `X × 10⁶` | NULL |
| `"Tới X triệu"` / `"Đến X triệu"` | NULL | `X × 10⁶` |
| `"X triệu"` | `X × 10⁶` | `X × 10⁶` |
| `"X - Y USD"` | `round(X × 26_000)` | `round(Y × 26_000)` |
| `"Thoả thuận"` / `"Negotiable"` | NULL | NULL |
| Khác | NULL | NULL |

`USD_TO_VND = 26_000`. Dùng `round()` tránh float drift. NULL/NULL → giữ `salary_raw` để display.

### Experience → REAL

| Pattern (lower-strip) | Output |
|---|---:|
| `"không yêu cầu"` / `"dưới 1 năm"` | `0.0` |
| `"1 năm"` … `"5 năm"` | `1.0` … `5.0` |
| `"trên 5 năm"` | `5.0` |
| Khác | NULL |

### Deadline → ISO date
`"DD/MM/YYYY"` → `"YYYY-MM-DD"`. Invalid → NULL.

### `xa_phuong` → `job_phuong` M:N
Mỗi phường trong `xa_phuong` → normalize (trim + collapse + lowercase prefix + title-case rest) → upsert `phuongs` → insert junction `job_phuong`. Không filter theo size hay location.

### Company
Normalize `name`: `re.sub(r'\s+', ' ', name.strip())` (giữ case). Upsert `companies`.

---

## VII · Agent → Data

| Agent | Đọc | Ghi |
|---|---|---|
| 1 · Supervisor | `messages` (`json_extract(metadata,'$.handled_by')`) | `messages.metadata.handled_by` (Mode 0) |
| 2 · Memory | full `messages`, `memory_facts` | `memory_facts` |
| 3 · Profile | full `messages`, `user_profile` | `user_profile` (trừ blacklist) |
| 4 · Goal Setting | `user_profile` (gồm `mbti_*`/`holland_*` để personalize câu hỏi) | `goal_*` slot |
| 5 · Assessment | static JSON, `user_profile` | `mbti_*`, `holland_*` |
| 6 · Career Advisor | `user_profile`, `memory_facts` | — |
| 7 · Skill Gap | `user_profile`, `jobs`, `job_skills`, `jobs_fts`, Qdrant `job_titles`, Tavily | — |
| 8 · Learning Path | `user_profile`, Tavily | — |
| 9 · Job Search | `user_profile`, `messages.metadata`, `jobs`, `companies`, `phuongs`, `loai_jobs`, M:N tables, `job_skills`, `jobs_fts`, Qdrant 2 collection, Tavily | `messages.metadata.last_search.filter` |
| 10 · Company | Tavily | — |
| 11-18 | TBD (Manager D/E/F) | — |
