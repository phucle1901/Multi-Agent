# Design Data — Schema toàn hệ thống

Bản thiết kế **toàn bộ data layer** của project: SQL schema + Qdrant collections + Static files.

File này **living document** — cập nhật khi discuss thêm agent mới (D/E/F TBD).

---

## 0 · Stack

| Layer | Công nghệ |
|---|---|
| Relational | **SQLite** (FTS5 built-in) |
| Vector | **Qdrant** |
| Embedding | OpenAI `text-embedding-3-small` — **1536 dim**, distance **cosine** |
| Static | JSON files trong `data/assessments/` |

### SQLite convention

| Khái niệm Postgres | SQLite tương đương |
|---|---|
| `BIGSERIAL` | `INTEGER PRIMARY KEY AUTOINCREMENT` |
| `TIMESTAMPTZ` | `TEXT` (ISO 8601, vd `2026-05-13T10:23:00Z`) |
| `DATE` | `TEXT` (ISO 8601, vd `2026-05-13`) — sortable as string |
| `ENUM(...)` | `TEXT CHECK(col IN ('a','b',...))` |
| `JSONB` | `TEXT` chứa JSON — query qua `json_extract`, `json_each` |
| `BOOLEAN` | `INTEGER` (0/1) |
| `tsvector + GIN` | `FTS5 virtual table` |

### PRAGMA bắt buộc khi mở connection

```sql
PRAGMA foreign_keys = ON;       -- bật FK enforcement (mặc định tắt!)
PRAGMA journal_mode = WAL;      -- write-ahead log, đọc-ghi đồng thời tốt hơn
PRAGMA synchronous = NORMAL;    -- balance an toàn / tốc độ
```

---

## I · SQL Schema

### Nhóm 1 — User & Runtime

#### `users`

Identity / authentication. Quản lý bởi app backend.

```sql
CREATE TABLE users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT UNIQUE NOT NULL,
    name        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

Auth fields (password_hash, oauth_provider...) — ngoài scope đồ án.

#### `conversations`

1 user có nhiều conversation. App backend tự ghi.

```sql
CREATE TABLE conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    mode        TEXT NOT NULL CHECK(mode IN 
                ('mode_0','mode_a','mode_b','mode_c','mode_d','mode_e','mode_f')),
    title       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_conv_user_updated ON conversations(user_id, updated_at DESC);
```

`mode` load-bearing — sidebar resume đúng mode khi user click thread cũ. Chi tiết 7 mode → [0.0-modes-and-communication.md](./0.0-modes-and-communication.md).

#### `messages`

Từng message trong conversation. App backend tự ghi mỗi turn.

```sql
CREATE TABLE messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    role            TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
    content         TEXT NOT NULL,
    metadata        TEXT NOT NULL DEFAULT '{}',   -- JSON string
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_msg_conv_created ON messages(conversation_id, created_at);
CREATE INDEX idx_msg_conv_handler_created ON messages(
    conversation_id, 
    json_extract(metadata, '$.handled_by'),
    created_at DESC
);
```

`metadata` JSON ví dụ:
```json
{
  "handled_by": "manager_c",
  "last_search": {"filter": {...}}
}
```

- `handled_by` ENUM (`supervisor` / `manager_a..f`) — gắn cho cả user msg + assistant msg cùng turn. Load-bearing cho Manager context filter. Chi tiết → [0.0-modes-and-communication.md](./0.0-modes-and-communication.md).
- `last_search.filter` cho Job Search refine — xem [09-job-search.md](./09-job-search.md).

#### `user_profile`

Slot-fill structured profile dài hạn. 1 row : 1 user. Ghi bởi **Agent 3 · Profile** (song song mỗi turn) — **trừ blacklist**.

```sql
CREATE TABLE user_profile (
    user_id                     INTEGER PRIMARY KEY REFERENCES users(id),

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
    hard_skills                 TEXT NOT NULL DEFAULT '[]',   -- ["SQL","Python","Tableau"]
    soft_skills                 TEXT NOT NULL DEFAULT '[]',
    languages                   TEXT NOT NULL DEFAULT '[]',   -- [{"lang":"English","level":"B2"}]
    certificates                TEXT NOT NULL DEFAULT '[]',

    -- Goal (Profile blacklist — chỉ Goal Setting set)
    goal_type                   TEXT CHECK(goal_type IS NULL OR goal_type IN 
                                ('career_change','promotion','first_job','skill_acquisition')),
    target_role                 TEXT,
    target_salary_min_vnd       INTEGER,
    target_salary_max_vnd       INTEGER,
    target_date                 TEXT,                          -- ISO date
    target_location             TEXT,

    -- Assessment (Profile blacklist — chỉ Assessment set)
    mbti_type                   TEXT,                          -- "INTJ"
    holland_code                TEXT,                          -- "RIA"
    mbti_completed_at           TEXT,
    holland_completed_at        TEXT,

    -- Job preferences
    work_mode                   TEXT CHECK(work_mode IS NULL OR work_mode IN 
                                ('remote','hybrid','onsite')),
    company_size_pref           TEXT CHECK(company_size_pref IS NULL OR company_size_pref IN 
                                ('startup','sme','large_corp')),
    preferred_industries        TEXT NOT NULL DEFAULT '[]',    -- ["fintech","edtech"]

    -- Meta
    created_at                  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at                  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

Tất cả slot nullable — fill dần qua hội thoại.

**Profile blacklist** (Profile KHÔNG bao giờ ghi, dù user nói rõ):
`goal_type`, `target_role`, `target_salary_min_vnd`, `target_salary_max_vnd`, `target_date`, `mbti_type`, `holland_code`, `mbti_completed_at`, `holland_completed_at`.

Backend khi user signup → INSERT row rỗng (mọi slot NULL, JSON arrays = `'[]'`).

Chi tiết → [03-profile.md](./03-profile.md).

#### `memory_facts`

Free-form fact dài hạn về user. Ghi bởi **Agent 2 · Memory**.

```sql
CREATE TABLE memory_facts (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                 INTEGER NOT NULL REFERENCES users(id),
    category                TEXT NOT NULL CHECK(category IN 
                            ('preference','context','emotion','interaction_meta')),
    content                 TEXT NOT NULL,
    source_conversation_id  INTEGER REFERENCES conversations(id),
    source_message_id       INTEGER REFERENCES messages(id),
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_mem_user_cat_updated ON memory_facts(user_id, category, updated_at DESC);
```

Hard delete (không soft-delete).

---

### Nhóm 2 — Jobs & Companies (offline / batch from crawl)

> **Phần CRITICAL — không sửa được sau khi import 14,833 jobs + index Qdrant.** Mọi cột `*_raw` giữ verbatim từ crawl; mọi cột parsed có thể re-derive từ raw nếu logic parsing thay đổi.

#### `companies`

```sql
CREATE TABLE companies (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT UNIQUE NOT NULL,
    size_raw     TEXT,                   -- "500-1000 nhân viên"
    field_raw    TEXT,                   -- "Sản xuất"
    address      TEXT,
    -- Derived (Pipeline 0)
    size_bucket  TEXT CHECK(size_bucket IS NULL OR size_bucket IN 
                 ('startup','sme','large_corp'))
);

CREATE INDEX idx_companies_field        ON companies(field_raw);
CREATE INDEX idx_companies_size_bucket  ON companies(size_bucket);
```

**Rule derive `size_bucket`** từ `size_raw` (để match `user_profile.company_size_pref`):
- Parse số nhân viên từ size_raw (vd "500-1000" → lấy số nhỏ nhất = 500)
- `< 50` → `startup`
- `50–500` → `sme`
- `> 500` → `large_corp`
- Không parse được → NULL

**Normalize name** trước UNIQUE check: trim + collapse whitespace. Không lowercase (giữ Title Case "FPT Software").

#### `phuongs` (master list phường/xã Hà Nội)

```sql
CREATE TABLE phuongs (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT UNIQUE NOT NULL          -- normalized: "phường Cầu Giấy", "xã Ba Vì"
);
```

**Normalize `name`**: lowercase prefix (`phường`/`xã`), title-case phần còn lại, single-space.
- `"phường lĩnh nam"` → `"phường Lĩnh Nam"`
- `"xã BA VÌ"` → `"xã Ba Vì"`

#### `loai_jobs` (master list ngành nghề từ topcv)

```sql
CREATE TABLE loai_jobs (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT UNIQUE NOT NULL          -- "Kinh doanh / Bán hàng" (verbatim)
);
```

#### `jobs` (core)

```sql
CREATE TABLE jobs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    source                  TEXT NOT NULL DEFAULT 'topcv',
    link_job                TEXT UNIQUE NOT NULL,
    company_id              INTEGER REFERENCES companies(id),

    -- Raw từ crawl (giữ verbatim) --
    title                   TEXT NOT NULL,
    location_raw            TEXT,                  -- "Hà Nội, và 2 nơi khác"
    work_location           TEXT,                  -- multi-line address
    work_time               TEXT,                  -- "Thứ 2 - Thứ 6..."
    work_type               TEXT,                  -- "Toàn thời gian"/"Bán thời gian"/"Thực tập"
    level_raw               TEXT,                  -- "Nhân viên"/"Trưởng phòng"
    quantity                TEXT,                  -- "10 người"
    application_method      TEXT,
    job_description         TEXT,
    requirements            TEXT,
    benefits                TEXT,
    salary_raw              TEXT,                  -- "60 - 100 triệu" / "Thoả thuận"
    experience_raw          TEXT,                  -- "5 năm" / "Không yêu cầu"
    deadline_raw            TEXT,                  -- "04/04/2026"

    -- Parsed (Pipeline 0, có thể re-derive) --
    salary_min              INTEGER,               -- VND/tháng, NULL nếu "Thoả thuận"/USD/không parse
    salary_max              INTEGER,
    experience_years        REAL,                  -- 0.0 = "Không yêu cầu", NULL = không parse
    deadline                TEXT,                  -- "YYYY-MM-DD"
    is_in_hanoi             INTEGER NOT NULL DEFAULT 0,    -- BOOL: location_raw chứa "Hà Nội"
    is_all_hn               INTEGER NOT NULL DEFAULT 0,    -- BOOL: xa_phuong ≥ 50 (crawl artifact, không có phường cụ thể)

    -- Extracted (offline LLM Pipeline 1, 2) --
    work_mode_extracted     TEXT CHECK(work_mode_extracted IS NULL OR work_mode_extracted IN 
                            ('remote','hybrid','onsite','unknown')),
    work_mode_extracted_at  TEXT,                  -- ISO timestamp, idempotent flag
    skills_extracted_at     TEXT,                  -- idempotent flag cho Pipeline 1

    -- Meta --
    crawled_at              TEXT NOT NULL
);

CREATE INDEX idx_jobs_company           ON jobs(company_id);
CREATE INDEX idx_jobs_salary_min        ON jobs(salary_min);
CREATE INDEX idx_jobs_salary_max        ON jobs(salary_max);
CREATE INDEX idx_jobs_deadline          ON jobs(deadline);
CREATE INDEX idx_jobs_exp               ON jobs(experience_years);
CREATE INDEX idx_jobs_work_mode         ON jobs(work_mode_extracted);
CREATE INDEX idx_jobs_in_hanoi          ON jobs(is_in_hanoi);
CREATE INDEX idx_jobs_source            ON jobs(source);
CREATE INDEX idx_jobs_skills_extracted  ON jobs(skills_extracted_at);
CREATE INDEX idx_jobs_wm_extracted      ON jobs(work_mode_extracted_at);
```

##### Vì sao có `is_in_hanoi` + `is_all_hn` (quan trọng — đọc kỹ)

`xa_phuong` trong `job_details.json` là **search filter scope của crawler** (filter HN khi crawl), **không phải** vị trí thật của job.

Ví dụ trong sample: `location: "Hồ Chí Minh, và 7 nơi khác"` nhưng `xa_phuong` liệt kê 96 phường HN → đây là crawl artifact, **không** nghĩa là job ở HN.

Pipeline 0 áp 3 rule:
- `is_in_hanoi = 1` nếu `location_raw` (lowercase) chứa `"hà nội"` / `"hanoi"`. Else `= 0`.
- `is_all_hn = 1` nếu `is_in_hanoi=1 AND len(xa_phuong) ≥ 50` — flag artifact, **KHÔNG** insert vào `job_phuong`.
- `is_in_hanoi=1 AND len(xa_phuong) < 50` → insert M:N bình thường (phường cụ thể, đáng tin).
- `is_in_hanoi=0` → **bỏ qua hoàn toàn** xa_phuong (search filter, không có ý nghĩa địa lý).

##### Query pattern (Job Search)

- **User filter phường X** (strict): chỉ jobs có ward khớp.
  ```sql
  ... AND EXISTS (
      SELECT 1 FROM job_phuong 
      WHERE job_id = jobs.id AND phuong_id = ?
  )
  ```
- **User filter generic HN** (không cụ thể ward): tất cả jobs HN bao gồm `is_all_hn`.
  ```sql
  ... AND is_in_hanoi = 1
  ```

`is_all_hn = 1` **không lôi vào filter phường cụ thể** — tránh false positive cho jobs không rõ ward.

#### `job_phuong` (M:N jobs ↔ phuongs)

```sql
CREATE TABLE job_phuong (
    job_id     INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    phuong_id  INTEGER NOT NULL REFERENCES phuongs(id),
    PRIMARY KEY (job_id, phuong_id)
);

CREATE INDEX idx_job_phuong_phuong ON job_phuong(phuong_id);
```

#### `job_loai_jobs` (M:N jobs ↔ loai_jobs)

```sql
CREATE TABLE job_loai_jobs (
    job_id   INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    loai_id  INTEGER NOT NULL REFERENCES loai_jobs(id),
    PRIMARY KEY (job_id, loai_id)
);

CREATE INDEX idx_job_loai_loai ON job_loai_jobs(loai_id);
```

#### `job_skills` (extract từ `requirements`, Pipeline 1)

```sql
CREATE TABLE job_skills (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    skill_name  TEXT NOT NULL,                            -- normalized: "Python", "Microsoft Excel"
    category    TEXT NOT NULL CHECK(category IN ('hard','soft','tool','certificate')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_job_skills_job  ON job_skills(job_id);
CREATE INDEX idx_job_skills_name ON job_skills(skill_name);
CREATE INDEX idx_job_skills_cat  ON job_skills(category);
```

Logic extract + normalize → Pipeline 1. Dùng bởi **Skill Gap (Agent 7)** + rerank trong **Job Search (Agent 9)**.

#### `jobs_fts` (FTS5 virtual table — BM25 title)

```sql
CREATE VIRTUAL TABLE jobs_fts USING fts5(
    title,
    content='jobs',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

-- Sync triggers
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

`tokenize='unicode61 remove_diacritics 2'` → bỏ dấu tiếng Việt khi index, user search `"Cau Giay"` vẫn match `"Cầu Giấy"`.

**Bulk import tip**: tạo FTS sau khi INSERT 14,833 jobs xong, dùng `INSERT INTO jobs_fts(jobs_fts) VALUES('rebuild')` nhanh hơn để trigger chạy từng dòng.

Dùng bởi: **Skill Gap (Agent 7)**, **Job Search (Agent 9)** — BM25 trên title.

---

## II · Qdrant Collections

Cả 2 collection cùng cấu hình vector:
```python
VectorParams(size=1536, distance=Distance.COSINE)
```

**Point ID = `jobs.id`** (integer) — đồng nhất giữa 2 collection và SQL → dễ JOIN, dễ retrieve theo `job_id IN (...)`.

### Collection 1 · `jobs` (full-doc embedding) — đã có sẵn

**Vector**: embedding của text build bởi [embedding/text_builder.py](../embedding/text_builder.py) — concat các field:
`title | company | salary | experience | level | work_type | location | loai_job | job_description | requirements | benefits`

**Payload (per point):**
```json
{
  "job_id":       123,
  "source":       "topcv",
  "title":        "Data Analyst",
  "company_name": "FPT Software",
  "salary_min":   15000000,
  "salary_max":   25000000,
  "is_in_hanoi":  true,
  "work_mode":    "hybrid",
  "deadline":     "2026-04-04"
}
```

**Indexed payload (filter-able):**
```python
qdrant.create_payload_index(
    collection_name="jobs",
    field_name="job_id",
    field_schema="integer"
)
```
Chỉ index `job_id` — đủ cho pattern Job Search (SQL hard-filter trước → Qdrant filter by `job_id IN (...)` → cosine rank). Các field khác lưu payload để display nhưng không index. Nếu sau cần filter standalone, `create_payload_index` runtime.

**Mục đích**: semantic search trên toàn bộ JD (cho Job Search rerank, Q&A về job).

### Collection 2 · `job_titles` (title-only embedding) — mới

**Vector**: embedding của text:
```
title | level_raw | loai_jobs concat
```

Vd: `"Data Analyst | Nhân viên | Phân tích dữ liệu / Data Analyst, IT phần mềm"`

**Payload (per point):**
```json
{
  "job_id":       123,
  "title":        "Data Analyst",
  "level_raw":    "Nhân viên",
  "loai_jobs":    ["Phân tích dữ liệu / Data Analyst", "IT phần mềm"],
  "source":       "topcv",
  "salary_min":   15000000,
  "salary_max":   25000000,
  "is_in_hanoi":  true,
  "deadline":     "2026-04-04"
}
```

**Indexed payload:**
```python
qdrant.create_payload_index(
    collection_name="job_titles",
    field_name="job_id",
    field_schema="integer"
)
```

**Mục đích**: semantic search role precision cao (loại nhiễu của full-doc embedding khi description dài át tín hiệu title). Dùng bởi:
- **Skill Gap (Agent 7)** Mode A — Stage 1 retrieval
- **Job Search (Agent 9)** — Stage 2 hybrid soft match

---

## III · Static Files (JSON)

Static content KHÔNG vào DB.

```
data/assessments/
  mbti_questions.json          # ~60 câu hỏi MBTI
  holland_questions.json       # ~60 câu hỏi Holland
  mbti_interpretations.json    # 16 type → schema cố định
  holland_interpretations.json # 6 letter → schema cố định
```

Dùng bởi **Agent 5 · Assessment**. Schema chi tiết → [05-assessment.md](./05-assessment.md).

Static file khác (resume templates, cover letter templates, question bank) — sẽ note sau khi brainstorm agent 13–18.

---

## IV · Parsing Rules — raw → structured (Pipeline 0)

### `salary_raw` → `(salary_min, salary_max)` VND/tháng

| Pattern raw | salary_min | salary_max |
|---|---|---|
| `"60 - 100 triệu"` / `"60-100 triệu"` | 60_000_000 | 100_000_000 |
| `"Trên 30 triệu"` / `"Từ 30 triệu"` | 30_000_000 | NULL |
| `"Đến 50 triệu"` / `"Tối đa 50 triệu"` | NULL | 50_000_000 |
| `"30 triệu"` (single value) | 30_000_000 | 30_000_000 |
| `"Thoả thuận"` / `"Cạnh tranh"` / `"Negotiable"` | NULL | NULL |
| `"1000 - 2000 USD"` / non-VND | NULL | NULL (giữ raw, không convert) |
| Pattern khác | NULL | NULL |

Trường hợp NULL/NULL → giữ `salary_raw` để display.

### `experience_raw` → `experience_years` REAL

| Pattern | Output |
|---|---|
| `"Không yêu cầu"` / `"Không YC"` | `0.0` |
| `"X năm"` (single) | `X.0` |
| `"X - Y năm"` (range) | `X.0` (lấy min — yêu cầu tối thiểu) |
| `"Trên X năm"` / `"Từ X năm"` | `X.0` |
| `"Dưới X năm"` | `0.0` |
| Không parse được | NULL |

### `deadline_raw` → `deadline` (ISO date)

- Format topcv: `DD/MM/YYYY` → `YYYY-MM-DD`
- `"04/04/2026"` → `"2026-04-04"`
- Invalid date (eg `"32/13/2026"`) → NULL

### `location_raw` → `is_in_hanoi` BOOL

- Lowercase + chứa `"hà nội"` / `"hanoi"` → `1`
- Else → `0`

### `xa_phuong` array → `job_phuong` M:N + `is_all_hn`

```
if is_in_hanoi == 0:
    skip xa_phuong (search filter artifact)
    is_all_hn = 0
elif len(xa_phuong) >= 50:
    is_all_hn = 1
    skip M:N insert
else:
    is_all_hn = 0
    for each phuong in xa_phuong:
        normalized = normalize_phuong(phuong)
        upsert phuongs(name=normalized) → phuong_id
        insert job_phuong(job_id, phuong_id)
```

### `loai_job` array → `job_loai_jobs` M:N

Straightforward: upsert master `loai_jobs(name)` (verbatim, không normalize), insert M:N.

### `company_name` + `company_size` + `company_field` → `companies`

Normalize name (trim + collapse whitespace), upsert by name. Derive `size_bucket` từ `size_raw` per rule trong section I.

---

## V · Data Pipelines (offline / batch)

### Pipeline 0 · Initial bulk import (1 lần, 14,833 jobs)

**Input**: `data/job_details.json`  
**Output**: SQL tables — `companies`, `phuongs`, `loai_jobs`, `jobs`, `job_phuong`, `job_loai_jobs`, `jobs_fts` (auto via trigger hoặc rebuild sau import)

Bước:
1. Validate JSON record (có `link_job` + `title` không) — skip nếu thiếu.
2. Upsert `companies` (normalize name), derive `size_bucket`.
3. Parse `salary_raw`, `experience_raw`, `deadline_raw`, `location_raw` per rule section IV.
4. Insert `jobs` (skip nếu `link_job` đã tồn tại — `UNIQUE`).
5. Upsert `loai_jobs` master + insert `job_loai_jobs` M:N.
6. Apply rule `xa_phuong`: nếu `is_in_hanoi=1 AND len<50` → upsert `phuongs` master (normalize) + insert `job_phuong` M:N.
7. Sau khi xong toàn bộ: `INSERT INTO jobs_fts(jobs_fts) VALUES('rebuild');` để build FTS một lần (nhanh hơn trigger từng dòng).

Idempotent qua `jobs.link_job UNIQUE`. Re-run = upsert.

### Pipeline 1 · Skill extract

**Trigger**: jobs có `skills_extracted_at IS NULL`

```
For each job (batch nhiều job/call để tiết kiệm):
  text = job.requirements + "\n\n" + job.job_description
  LLM extract → list[{skill_name, category}] (normalize theo canonical list)
  INSERT INTO job_skills (job_id, skill_name, category)
  UPDATE jobs SET skills_extracted_at = datetime('now') WHERE id = job.id
```

Canonical skill list ở prompt — xem [prompt-conventions.md](./prompt-conventions.md). Dùng `job_id` + `skill_name` để dedup nếu re-run (DELETE rồi INSERT theo job_id, hoặc check existence trước).

**Cost estimate**: 14,800 jobs initial. Daily ~100-500 jobs mới.

### Pipeline 2 · Work mode extract

**Trigger**: jobs có `work_mode_extracted_at IS NULL`

```
PHA 1 — keyword pass:
  text = title + job_description + benefits + work_time + work_location
  If match ["remote","WFH","work from home","tại nhà","làm việc tại nhà"]:
    work_mode_extracted = 'remote'
  
PHA 2 — LLM ambiguous (chỉ chạy khi text có ["hybrid","linh hoạt","online","từ xa"]):
  LLM judge: hybrid mode (vị trí) hay flexible HOURS?
  → 'hybrid' hoặc 'onsite'
  
Else default → 'onsite' (HN baseline)

UPDATE jobs SET work_mode_extracted = ?, work_mode_extracted_at = datetime('now')
```

**Lý do 2-pha**: `"linh hoạt"` ~8.3% jobs nhưng đa số chỉ giờ giấc, không phải vị trí → tách pha LLM tiết kiệm cost.

### Pipeline 3 · Embed full-doc → Qdrant `jobs`

**Trigger**: jobs chưa có point trong Qdrant `jobs` (check by point_id = `jobs.id`)

```
For each job (batch 200):
  text = text_builder.build_embedding_text(job_dict_from_sql)
  vector = openai.embed(text)
  qdrant.upsert(
    collection="jobs",
    point_id = job.id,
    vector = vector,
    payload = {job_id, source, title, company_name, salary_min, salary_max, is_in_hanoi, work_mode, deadline}
  )
```

Code hiện tại trong [embedding/](../embedding/) — pipeline đang đọc từ JSON, **cần chuyển sang đọc từ SQL** sau Pipeline 0 import.

### Pipeline 4 · Embed title → Qdrant `job_titles`

**Trigger**: jobs chưa có point trong Qdrant `job_titles`

```
For each job (batch 200):
  loai_str = " / ".join(SELECT name FROM loai_jobs JOIN job_loai_jobs ON ... WHERE job_id = job.id)
  text = f"{job.title} | {job.level_raw or ''} | {loai_str}"
  vector = openai.embed(text)
  qdrant.upsert(
    collection="job_titles",
    point_id = job.id,
    vector = vector,
    payload = {job_id, title, level_raw, loai_jobs, source, salary_min, salary_max, is_in_hanoi, deadline}
  )
```

### Thứ tự chạy

```
Pipeline 0 (import SQL)
    ↓
    ├──→ Pipeline 1 (skill extract)        — chạy parallel
    ├──→ Pipeline 2 (work_mode extract)    — chạy parallel
    ├──→ Pipeline 3 (embed jobs)           — chạy parallel
    └──→ Pipeline 4 (embed job_titles)     — chạy parallel
```

Pipeline 1-4 độc lập, có thể chạy song song. Mỗi pipeline idempotent qua flag `*_extracted_at` hoặc check existence trong Qdrant.

---

## VI · Mapping Agent → Data

| Agent | Đọc | Ghi |
|---|---|---|
| 1 · Supervisor | `messages` (user msg + handled_by breadcrumb) | `messages.metadata.handled_by` (UPDATE user msg) |
| 2 · Memory | `messages`, `memory_facts` | `memory_facts` |
| 3 · Profile | `messages`, `user_profile` | `user_profile` — **trừ** `goal_*`, `mbti_*`, `holland_*`, `*_completed_at` (blacklist) |
| 4 · Goal Setting | `user_profile` | `user_profile` (`goal_type`, `target_role`, `target_salary_min/max_vnd`, `target_date`) |
| 5 · Assessment | static JSON, `user_profile` | `user_profile` (`mbti_type`, `holland_code`, `*_completed_at`) |
| 6 · Career Advisor | `user_profile`, `memory_facts` | — |
| 7 · Skill Gap | `user_profile`, `jobs`, `job_skills`, `jobs_fts`, Qdrant `job_titles`, Tavily | — |
| 8 · Learning Path | `user_profile`, Tavily | — |
| 9 · Job Search | `user_profile`, `messages.metadata` (previous filter), `jobs`, `companies`, `phuongs`, `loai_jobs`, `job_phuong`, `job_loai_jobs`, `job_skills`, `jobs_fts`, Qdrant `jobs` + `job_titles`, Tavily | `messages.metadata.last_search.filter` |
| 10 · Company | Tavily | — (stateless) |
| 11–18 | TBD (D/E/F brainstorm sau) | |

---

## VII · TODO cho phase sau

- **Manager D** (11 Market Insight, 12 Salary): khả năng dùng aggregate `jobs` (GROUP BY level/role/loai_jobs) — **không cần bảng mới**, nhưng cần index trên cột aggregate. Sẽ note khi brainstorm.
- **Manager E** (13 CV Parser, 14 Resume Builder, 15 Cover Letter): cần bảng mới `user_cvs(user_id, file_path, parsed_json, uploaded_at)` + static templates trong `data/templates/`.
- **Manager F** (16 Question Gen, 17 Mock Interview, 18 Negotiation): static question bank JSON hay LLM live — quyết khi brainstorm.

---

## VIII · Quyết định khoá

| Vấn đề | Quyết định |
|---|---|
| Relational DB | SQLite (FTS5 built-in) |
| Vector DB | Qdrant |
| Embedding model | OpenAI `text-embedding-3-small`, 1536 dim, cosine |
| Date/time storage | ISO 8601 TEXT |
| JSON arrays | TEXT chứa JSON, query qua `json_extract` |
| ENUM | TEXT + CHECK (trừ `jobs.source` — bỏ CHECK để dễ thêm crawler) |
| Multi-user | Mọi bảng user-scoped FK → `users.id` |
| Bảng cache | KHÔNG — tính được live thì tính live |
| Persist output stateless agent | KHÔNG (Mock Interview, Learning Path, Negotiation) |
| Static content | JSON files trong `data/` |
| Qdrant scope | 2 collection (`jobs`, `job_titles`), point_id = `jobs.id` |
| Qdrant indexed payload | Chỉ `job_id` (filter pattern qua SQL → Qdrant `job_id IN ...`) |
| `conversations.mode` | Bắt buộc — UX sidebar resume |
| `messages.metadata.handled_by` | JSON, indexed expression `(conv_id, handled_by, created_at)` |
| `is_in_hanoi` + `is_all_hn` | Bắt buộc — xử lý crawl artifact `xa_phuong` |
| FTS5 scope | Title only, tokenize `unicode61 remove_diacritics 2` |
| `companies.size_bucket` | Derived (startup/sme/large_corp) cho filter user prefs |
| `jobs.source` | DEFAULT `'topcv'`, không CHECK constraint |
| Profile blacklist | `goal_*`, `mbti_*`, `holland_*`, `*_completed_at` |
| PRAGMA bật mỗi connection | `foreign_keys=ON`, `journal_mode=WAL`, `synchronous=NORMAL` |
