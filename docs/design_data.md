# Design Data — Schema toàn hệ thống

Bản thiết kế **toàn bộ data layer** của project: SQL schema + Qdrant collections + Static files.

File này **living document** — cập nhật khi discuss thêm agent mới.

---

## Nguyên tắc

1. **Multi-user**: mọi bảng user-scoped FK → `users.id`.
2. **Không tạo bảng cache**: tính được live thì tính live.
3. **Không persist output stateless agent** (Mock Interview, Learning Path, Negotiation).
4. **Static content → file JSON** (MBTI/Holland questions, resume templates), không vào DB.
5. **Qdrant scope hạn chế**: chủ yếu cho `jobs`. Collection khác phải justify rõ.

---

## I · SQL Schema

### Nhóm 1 — User & Conversation (runtime)

#### `users`

Identity / authentication. Quản lý bởi app backend.

| Column | Type | Note |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `email` | TEXT UNIQUE NOT NULL | |
| `name` | TEXT | |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ DEFAULT now() | |

> Field auth (password_hash, oauth_provider...) tuỳ stack — không spec ở đây.

#### `conversations`

1 user có nhiều conversation. App backend tự ghi.

| Column | Type | Note |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `user_id` | BIGINT FK users.id NOT NULL | |
| `title` | TEXT | (optional) tóm tắt nội dung |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ DEFAULT now() | |

Index: `(user_id, updated_at DESC)`.

#### `messages`

Từng message trong conversation. App backend tự ghi mỗi turn.

| Column | Type | Note |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `conversation_id` | BIGINT FK conversations.id NOT NULL | |
| `role` | ENUM('user','assistant','system') NOT NULL | |
| `content` | TEXT NOT NULL | |
| `metadata` | JSONB DEFAULT `'{}'` | structured info, vd `{"handled_by": "manager_c", "last_search": {"filter": {...}}}`. `handled_by` ENUM `supervisor`/`manager_a..f` — đánh dấu agent xử lý turn, để filter per-group context. `last_search.filter` cho Job Search refine — xem doc agent 9 |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |

Index: `(conversation_id, created_at)`.

#### `user_profile`

Slot-fill structured profile dài hạn. 1 row : 1 user. Ghi bởi **Agent 3 · Profile** (song song mỗi turn).

| Column | Type | Note |
|---|---|---|
| `user_id` | BIGINT **PK** FK users.id | |
| **— Education —** | | |
| `highest_degree` | ENUM('high_school','college','university','master','phd') | nullable |
| `major` | TEXT | nullable |
| `school` | TEXT | nullable |
| `graduation_year` | INT | nullable |
| `gpa` | NUMERIC(3,2) | nullable |
| **— Experience (current only) —** | | |
| `years_experience` | INT | nullable |
| `current_role` | TEXT | nullable |
| `current_company` | TEXT | nullable |
| `current_salary_vnd_month` | BIGINT | VND/tháng |
| `employment_status` | ENUM('employed','unemployed','student','freelancer') | nullable |
| **— Skills (JSON arrays) —** | | |
| `hard_skills` | JSONB DEFAULT `'[]'` | `["SQL","Python","Tableau"]` |
| `soft_skills` | JSONB DEFAULT `'[]'` | `["communication","leadership"]` |
| `languages` | JSONB DEFAULT `'[]'` | `[{"lang":"English","level":"B2"}]` |
| `certificates` | JSONB DEFAULT `'[]'` | `["AWS SAA","PMP"]` |
| **— Goal —** | | |
| `goal_type` | ENUM('career_change','promotion','first_job','skill_acquisition') | nullable |
| `target_role` | TEXT | "Data Analyst" |
| `target_salary_min_vnd` | BIGINT | VND/tháng |
| `target_salary_max_vnd` | BIGINT | VND/tháng |
| `target_date` | DATE | deadline đạt goal |
| `target_location` | TEXT | "Cầu Giấy" / "Hà Nội" / "remote" |
| **— Assessment —** | | |
| `mbti_type` | CHAR(4) | "INTJ" |
| `holland_code` | CHAR(3) | "RIA" |
| `mbti_completed_at` | TIMESTAMPTZ | |
| `holland_completed_at` | TIMESTAMPTZ | |
| **— Job preferences —** | | |
| `work_mode` | ENUM('remote','hybrid','onsite') | nullable |
| `company_size_pref` | ENUM('startup','sme','large_corp') | nullable |
| `preferred_industries` | JSONB DEFAULT `'[]'` | `["fintech","edtech"]` |
| **— Meta —** | | |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ DEFAULT now() | |

Tất cả slot **nullable** — fill dần qua hội thoại.

Ghi: Agent 3 · Profile. Đọc: phần lớn agent nghiệp vụ.

#### `memory_facts`

Free-form fact dài hạn về user. Ghi bởi **Agent 2 · Memory**.

| Column | Type | Note |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `user_id` | BIGINT FK users.id NOT NULL | |
| `category` | ENUM('preference','context','emotion','interaction_meta') NOT NULL | |
| `content` | TEXT NOT NULL | 1 câu tự nhiên, ngắn (≤ ~200 char) |
| `source_conversation_id` | BIGINT FK conversations.id NULL | debug / audit |
| `source_message_id` | BIGINT FK messages.id NULL | debug / audit |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ DEFAULT now() | |

Index chính: `(user_id, category, updated_at DESC)`.

Hard delete (không soft-delete).

---

### Nhóm 2 — Jobs & Companies (offline/batch from crawl)

#### `companies`

Công ty từ pha crawl.

| Column | Type | Note |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `name` | TEXT UNIQUE NOT NULL | |
| `size` | TEXT | "500-1000 nhân viên" (raw từ crawl) |
| `field` | TEXT | "Sản xuất" (raw từ crawl) |
| `address` | TEXT | |

#### `phuongs`

Master list phường / xã Hà Nội.

| Column | Type | Note |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `name` | TEXT UNIQUE NOT NULL | "phường Cầu Giấy", "xã Ba Vì" |

#### `loai_jobs`

Master list ngành nghề (loai_job từ topcv).

| Column | Type | Note |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `name` | TEXT UNIQUE NOT NULL | "Kinh doanh / Bán hàng" |

#### `jobs`

Core table — jobs đã crawl.

| Column | Type | Note |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `source` | ENUM('topcv','itviec','linkedin','vietnamworks',...) NOT NULL DEFAULT 'topcv' | Multi-source ready |
| `link_job` | TEXT UNIQUE NOT NULL | URL gốc |
| `company_id` | BIGINT FK companies.id | |
| **— Core fields (raw from crawl) —** | | |
| `title` | TEXT | |
| `location` | TEXT | "Hà Nội, và 2 nơi khác" (raw) |
| `work_location` | TEXT | multi-line text (raw) |
| `work_time` | TEXT | "Thứ 2 - Thứ 6..." (raw) |
| `work_type` | TEXT | "Toàn thời gian" / "Bán thời gian" / "Thực tập" |
| `level` | TEXT | "Nhân viên", "Trưởng phòng"... (raw, không chuẩn hoá) |
| `quantity` | TEXT | "10 người" |
| `application_method` | TEXT | |
| `job_description` | TEXT | long-form |
| `requirements` | TEXT | long-form |
| `benefits` | TEXT | long-form |
| **— Parsed fields —** | | |
| `salary_raw` | TEXT | "13-18 triệu" / "Thoả thuận" |
| `salary_min` | BIGINT | VND/tháng (parsed) — NULL nếu "Thoả thuận" |
| `salary_max` | BIGINT | VND/tháng (parsed) — NULL nếu "Thoả thuận" |
| `experience_raw` | TEXT | "1 năm" / "Không yêu cầu" |
| `experience_years` | NUMERIC(3,1) | (parsed) — NULL nếu không xác định |
| `deadline_raw` | TEXT | "03/04/2026" |
| `deadline` | DATE | (parsed) |
| **— Extracted fields (offline LLM pipeline) —** | | |
| `work_mode_extracted` | ENUM('remote','hybrid','onsite','unknown') | extract từ description, xem [Pipeline 2](#pipeline-2--work-mode-extract) |
| `work_mode_extracted_at` | TIMESTAMPTZ | idempotent flag |
| `skills_extracted_at` | TIMESTAMPTZ | idempotent flag cho [Pipeline 1](#pipeline-1--skill-extract) |
| **— Meta —** | | |
| `crawled_at` | TIMESTAMPTZ | |

Index:
- `(salary_min)`, `(salary_max)`, `(deadline)`, `(level)`, `(experience_years)`, `(work_mode_extracted)`, `(source)`
- `(company_id)`

#### `job_phuong`

M:N giữa jobs ↔ phuongs.

| Column | Type | Note |
|---|---|---|
| `job_id` | BIGINT FK jobs.id ON DELETE CASCADE | |
| `phuong_id` | BIGINT FK phuongs.id | |
| | PRIMARY KEY (job_id, phuong_id) | |

Index: `(phuong_id)`.

#### `job_loai_jobs`

M:N giữa jobs ↔ loai_jobs.

| Column | Type | Note |
|---|---|---|
| `job_id` | BIGINT FK jobs.id ON DELETE CASCADE | |
| `loai_id` | BIGINT FK loai_jobs.id | |
| | PRIMARY KEY (job_id, loai_id) | |

Index: `(loai_id)`.

#### `job_skills`

Skill đã extract từ `requirements`. Normalize sẵn tên skill. Ghi bởi [Pipeline 1](#pipeline-1--skill-extract).

| Column | Type | Note |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `job_id` | BIGINT FK jobs.id ON DELETE CASCADE NOT NULL | |
| `skill_name` | TEXT NOT NULL | đã normalize ("Python", "Microsoft Excel"...) |
| `category` | ENUM('hard','soft','tool','certificate') NOT NULL | |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |

Index: `(job_id)`, `(skill_name)`, `(category)`.

Dùng bởi: **Skill Gap (Agent 7)**.

#### `jobs_fts` — Full-text search virtual table

PostgreSQL: dùng `tsvector` column + GIN index.
SQLite (hiện tại): FTS5 virtual table.

**PostgreSQL version**:
```sql
ALTER TABLE jobs ADD COLUMN search_tsv tsvector;
CREATE INDEX idx_jobs_search_tsv ON jobs USING GIN(search_tsv);

-- Trigger update tsv:
-- search_tsv = title*A + job_description*B + requirements*B + benefits*C + company_name*B
```

Dùng bởi: **Skill Gap (Agent 7)**, **Job Search (Agent 9)** — BM25-like search trên title.

---

## II · Qdrant Collections

### Collection 1 · `jobs` (hiện có)

Full-doc embedding.

- **Vector**: OpenAI `text-embedding-3-small` (1536 dim) — embed text built từ `text_builder.py` (title + company + salary + experience + level + work_type + location + loai_job + job_description + requirements + benefits)
- **Payload**: `{job_id, title, company_name, location, salary_min, salary_max, deadline}`
- **Mục đích**: semantic search trên toàn bộ JD

### Collection 2 · `job_titles` (mới)

Title-only embedding cho precision retrieval.

- **Vector**: OpenAI `text-embedding-3-small` — embed `title + " | " + level + " | " + loai_jobs concat`
- **Payload**: `{job_id, title, level, location, salary_min, salary_max, deadline, source}`
- **Mục đích**: semantic search role precision cao (loại nhiễu của full-doc)

Dùng bởi: **Skill Gap (Agent 7)**, **Job Search (Agent 9)**.

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

Dùng bởi: **Agent 5 · Assessment**.

Các static file khác sẽ note sau khi discuss agent 13-18 (resume templates, cover letter templates, ...).

---

## IV · Data Pipelines (offline / batch)

### Crawl pipeline

- **Tần suất**: 1 ngày 1 lần
- **Scope hiện tại**: topcv (Hà Nội)
- **Scope tương lai**: itviec, linkedin, vietnamworks (multi-source ready qua cột `source`)
- **Output**: INSERT/UPDATE bảng `jobs` + `companies` + `phuongs` + `loai_jobs` + `job_phuong` + `job_loai_jobs`
- **Idempotent**: dedup theo `link_job` (UNIQUE)

### Pipeline 1 · Skill extract

**Trigger**: sau crawl, chạy cho jobs có `skills_extracted_at IS NULL`.

**Logic**:
```
For each job:
  text = job.requirements + job.job_description
  LLM extract skill list:
    - Phân loại hard / soft / tool / certificate
    - Normalize tên theo canonical list (vd "Python 3.8" → "Python")
  INSERT INTO job_skills (job_id, skill_name, category) ...
  UPDATE jobs SET skills_extracted_at = now() WHERE id = job.id
```

**Normalize strategy**: prompt LLM cung cấp canonical skill list (Python, JavaScript, SQL, PostgreSQL, Tableau, Power BI, MS Excel, ...). LLM ưu tiên tên trong list.

**Cost estimate**: ~14,800 jobs initial run. Daily ~100-500 jobs mới. Có thể batch nhiều job/call.

### Pipeline 2 · Work mode extract

**Trigger**: sau crawl, chạy cho jobs có `work_mode_extracted_at IS NULL`.

**2-pha**:

```
PHA 1 — Keyword pass:
  text = title + job_description + benefits + work_time + work_location
  Match keywords ["remote","WFH","work from home","tại nhà","làm việc tại nhà"]
  Nếu match → work_mode_extracted = 'remote' (~4.2% jobs)

PHA 2 — LLM pass cho ambiguous:
  Nếu text có ["hybrid","linh hoạt","online","từ xa"]:
    LLM judge: hybrid mode hay flexible HOURS?
    → 'hybrid' hoặc 'onsite'
  Else:
    → 'onsite' (default HN)

UPDATE jobs SET work_mode_extracted_at = now()
```

**Lý do 2-pha**: "linh hoạt" rất noisy (8.3% jobs nhưng đa số chỉ là giờ giấc). Tiết kiệm LLM call.

**Cost estimate**: ~1,200 LLM call pha 2 (jobs có "linh hoạt/hybrid").

### Pipeline 3 · Qdrant indexing — `jobs` collection (full-doc)

**Trigger**: sau crawl, embed jobs mới.

**Logic**: dùng `text_builder.py` build full text → embed → upsert Qdrant.

### Pipeline 4 · Qdrant indexing — `job_titles` collection (mới)

**Trigger**: sau crawl, embed jobs mới.

**Logic**:
```
text = job.title + " | " + (job.level or "") + " | " + (loai_jobs concat)
vector = embed(text)
qdrant.upsert(collection='job_titles', point={
  id: job.id,
  vector,
  payload: {job_id, title, level, location, salary_min, salary_max, deadline, source}
})
```

---

## V · Mapping Agent → Data

| Agent | Đọc | Ghi |
|---|---|---|
| 1 · Supervisor | `messages` | — |
| 2 · Memory | `messages`, `memory_facts` | `memory_facts` |
| 3 · Profile | `messages`, `user_profile` | `user_profile` |
| 4 · Goal Setting | `user_profile` | `user_profile` (goal fields) |
| 5 · Assessment | static JSON, `user_profile` | `user_profile` (mbti/holland) |
| 6 · Career Advisor | `user_profile`, `memory_facts` | — |
| 7 · Skill Gap | `user_profile`, `jobs`, `job_skills`, `jobs_fts`, Qdrant `job_titles` | — |
| 8 · Learning Path | `user_profile` | — |
| 9 · Job Search | `user_profile`, `messages.metadata` (đọc previous filter), `jobs`, `companies`, `job_phuong`, `job_loai_jobs`, `loai_jobs`, `job_skills`, `jobs_fts`, Qdrant `job_titles`, **Tavily** | `messages.metadata.last_search.filter` |
| 10-18 · TBD | (sẽ bổ sung khi discuss) | |

---

## VI · TODO khi discuss tiếp các agent

- 10 · Company — cần Qdrant collection cho companies?
- 11 · Market Insight — aggregate jobs table?
- 12 · Salary — aggregate salary_min/max?
- 13 · CV Parser — bảng `user_cvs` lưu CV upload?
- 14 · Resume Builder — static template JSON?
- 15 · Cover Letter — static template JSON?
- 16-18 · Phỏng vấn & Đàm phán — bảng question bank? static?

File này sẽ update khi quyết định.
