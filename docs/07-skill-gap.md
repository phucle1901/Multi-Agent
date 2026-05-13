# Agent 7 · Skill Gap

## Mục đích

Giúp user biết **đang thiếu skill gì** so với 1 mục tiêu cụ thể. Mục tiêu có thể là:

- **1 role text** (vd "Data Analyst") — aggregate skill từ nhiều JD trong DB
- **1 job cụ thể** (URL / job_id / raw JD text) — extract skill từ chính JD đó

Output là `missing_skills` chi tiết (phân loại + priority + sources).

## Vị trí trong kiến trúc

Sub-agent của **Manager B · Tư vấn nghề nghiệp**. Gọi bởi Manager B (không trực tiếp từ Supervisor / UI).

Phân biệt với Career Advisor (Agent 6):
- **CA**: định hướng role nào phù hợp với user (tổng thể nhiều dimension)
- **Skill Gap**: với role/job đã xác định → liệt kê skill thiếu (chỉ trục skill, đi sâu)

## 2 Mode

| Mode | Trigger (Manager B detect) | Input | Cách xử lý |
|---|---|---|---|
| **A · By Role** | Message text về 1 role chung | `target_role: text` | Hybrid retrieval DB → aggregate frequency → priority bucket |
| **B · By Job** | URL / job_id / raw JD text dài | `{job_id?, url?, raw_text?}` | LLM extract trực tiếp từ JD đó → so sánh |

Heuristic detect mode:
- Message có URL → Mode B
- Message có `job_id` (user click 1 job card từ kết quả Job Search trước đó) → Mode B
- Raw text dài (>500 char, có dạng JD) → Mode B
- Còn lại → Mode A

## Input / Output

| | |
|---|---|
| **Input** | `mode` + `target` (role text HOẶC job ref) + user profile (`hard_skills`, `soft_skills`, `certificates`) + recent messages |
| **Output (success)** | `{mode, missing_skills, matched_skills, sources, source_type, caveat}` cho Manager B render |
| **Output (ask)** | Nếu không có target → ask back |

### Cấu trúc output

**Mode A**:
```json
{
  "mode": "by_role",
  "target_role": "Data Analyst",
  "current_skills": ["Python", "SQL cơ bản"],
  "missing_skills": [
    {"name": "Power BI",   "category": "tool", "priority": "must-have",   "frequency": 0.73},
    {"name": "Statistics", "category": "hard", "priority": "should-have", "frequency": 0.40},
    {"name": "Stakeholder communication", "category": "soft", "priority": "nice-to-have", "frequency": 0.20}
  ],
  "matched_skills": ["Python", "SQL"],
  "source_type": "internal",            // "internal" | "tavily" | "hybrid"
  "sources": [
    {"job_id": 123, "title": "Data Analyst - FPT", "url": "..."},
    ...
  ],
  "n_jobs_used": 18,
  "caveat": null
}
```

**Mode B**:
```json
{
  "mode": "by_job",
  "job_ref": {"job_id": 123},           // hoặc {url: "..."} / {raw_text: "..."}
  "job_title": "Data Analyst",
  "company": "FPT Software",
  "current_skills": ["Python", "SQL cơ bản"],
  "missing_skills": [
    {"name": "Power BI", "category": "tool", "priority": "must-have",
     "evidence": "Yêu cầu thành thạo Power BI để build dashboard"}
  ],
  "matched_skills": ["Python", "SQL"],
  "source_type": "specific_job",
  "caveat": null
}
```

## Data sources

| Nguồn | Vai trò | Mode dùng |
|---|---|---|
| `user_profile` (SQL) | Skill user hiện có | A, B |
| Recent messages | Bắt skill user vừa nhắc (Profile chưa kịp update) | A, B |
| `jobs` (SQLite) | JD thực tại HN | A (search), B (nếu input là job_id) |
| `job_skills` (bảng mới) | Skill đã pre-extract từ requirements | A |
| `jobs_fts` (FTS5) | BM25 search title | A (Stage 1 keyword) |
| Qdrant `job_titles` (collection mới) | Semantic search title-only | A (Stage 1 semantic) |
| Tavily Search | Fallback khi DB ít data | A (Stage 5 fallback) |
| Tavily Extract | Lấy full content từ URL | B (khi input là URL) |

## Mode A · Flow xử lý

```
1. Skill Gap nhận target_role + user context
   │  Nếu thiếu target_role → ask back
   │
2. RETRIEVAL (Stage 1) — hybrid 2 nhánh song song:
   │  ├─ FTS5 BM25 trên jobs_fts (field title) → top 30 jobs
   │  └─ Qdrant semantic trên collection job_titles → top 30 jobs
   │
3. FUSION (Stage 2) — Reciprocal Rank Fusion:
   │  combined_score = 1/(60+rank_fts) + 1/(60+rank_qdrant)
   │  Filter jobs có combined_score >= T
   │  ├─ count >= K → Stage 3
   │  └─ count < K  → Stage 5 (Tavily fallback)
   │
4. VERIFY (Stage 3) — LLM batched call:
   │  "Trong các title sau, cái nào THỰC SỰ là role {target_role}?"
   │  → loại false positive (vd "Business Analyst" lọt vào query "Data Analyst")
   │
5. AGGREGATE (Stage 4):
   │  JOIN job_skills cho jobs đã verified
   │  GROUP BY skill_name, count frequency
   │  Phân priority:
   │    freq >= 50%   → must-have
   │    25-50%        → should-have
   │    < 25%         → nice-to-have
   │
6. COMPARE với current_skills (merge profile + recent messages, LLM reconcile)
   │  missing = required - current
   │  matched = required ∩ current
   │
7. (Fallback Stage 5) TAVILY khi count < K:
      Tavily Search V2 config (xem mục Tavily config) → 5-8 JD page
      LLM extract skill list từ raw_content (frequency theo số nguồn)
      source_type = "tavily"
      caveat = "Database HN có ít data về role này, bổ sung từ web"
```

## Mode B · Flow xử lý

```
1. Lấy JD text:
   ├─ Nếu job_id (internal) → SELECT title, job_description, requirements, benefits FROM jobs WHERE id=?
   ├─ Nếu URL → Tavily Extract API (1 URL, full content)
   └─ Nếu raw text → dùng trực tiếp

2. LLM extract required skills từ JD đó:
   - hard / soft / tool / certificate
   - Priority infer từ wording của JD:
     • "bắt buộc" / "must have" / "yêu cầu" → must-have
     • "ưu tiên" / "preferred" / "is a plus" → nice-to-have
     • Còn lại                              → should-have
   - Mỗi skill kèm evidence (câu trích từ JD)

3. Compare với current_skills (merge profile + recent messages)
   missing = required - current
   matched = required ∩ current

4. Output (xem cấu trúc Mode B ở trên)
```

## Tavily config (khi fallback / extract)

### Tavily Search (Mode A fallback)

```python
TavilySearchResults(
    max_results=8,
    search_depth="advanced",
    include_raw_content=True,
    include_domains=[
        "linkedin.com", "vn.linkedin.com",
        "itviec.com", "topcv.vn",
        "vietnamworks.com", "topdev.vn",
    ],
)

query = f'"{target_role}" ("yêu cầu" OR "requirements" OR "job description") Hà Nội'
```

Cấu hình này đã được test thực tế: 7/8 result là JD thật, raw_content 20-33k chars/JD, đa số tại Hà Nội. Loại được blog ads / course ads / index page.

### Tavily Extract (Mode B URL)

Gọi endpoint `/extract` với 1 URL → trả full content. Verify wrapper LangChain ở pha implement; nếu không có thì gọi REST trực tiếp.

## Schema impact

### Bảng mới: `job_skills`

```sql
CREATE TABLE job_skills (
    id           BIGSERIAL PRIMARY KEY,
    job_id       INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    skill_name   TEXT NOT NULL,         -- đã normalize sẵn từ pha extract
    category     TEXT NOT NULL,         -- 'hard' | 'soft' | 'tool' | 'certificate'
    created_at   TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_job_skills_job  ON job_skills(job_id);
CREATE INDEX idx_job_skills_name ON job_skills(skill_name);
CREATE INDEX idx_job_skills_cat  ON job_skills(category);
```

Logic extract + normalize **không thuộc agent này** — sẽ build ở module data (thảo luận khi đã xác định scope hết các agent).

### Qdrant collection mới: `job_titles`

- Vector: embed `title` (+ optional `level`, `loai_jobs` concat)
- Payload: `{job_id, title, level, location}`
- Mục đích: semantic search precision cao hơn full-doc embedding hiện có

Build pipeline (embed + upsert) thuộc module data.

### KHÔNG thay đổi schema user-side

Skill Gap KHÔNG tạo bảng cache, KHÔNG persist output, KHÔNG ghi vào `user_profile`.

## Tham số

| Param | Mặc định | Ý nghĩa |
|---|---|---|
| `top_n_per_branch` | 30 | Top jobs lấy ra ở mỗi nhánh retrieval (Mode A) |
| `score_threshold T` | TBD | Min combined_score để jobs được giữ lại |
| `min_jobs K` | 5 | Số jobs tối thiểu để KHÔNG fallback Tavily |
| `priority_threshold` | 50% / 25% | Cắt must / should / nice (Mode A) |

Giá trị cụ thể tinh chỉnh sau khi test thực tế.

## Edge cases

| Case | Xử lý |
|---|---|
| Không có target (cả role và job) | Ask back: "Bạn muốn so sánh skill với role nào, hoặc paste link/text JD?" |
| Profile rỗng skill | `current_skills = []`, `missing_skills = all required`. Caveat: "Profile bạn chưa có skill nào, mình giả định xuất phát từ 0" |
| Mode A: DB < K jobs match | Fallback Tavily — `source_type = "tavily"` + caveat |
| Mode A: Stage 3 LLM verifier loại hết jobs | Treat như "DB ít" → fallback Tavily |
| Mode A: Cả DB lẫn Tavily đều ít data | Output low-confidence, LLM dùng knowledge nội bộ + caveat "data hạn chế" |
| Mode A: Target_role lạ/niche (vd "AI Ethics Officer") | Stage 1 → 0 result → fallback Tavily ngay |
| Mode B: URL không crawl được | Caveat + ask user paste text |
| Mode B: job_id không tồn tại | Ask back: "Không tìm thấy job này, bạn paste link/text được không?" |
| Mode B: Raw text quá ngắn (<200 char) | Ask back: "Đây có phải JD không? Bạn paste đầy đủ hơn?" |
| Mode B: JD không có section requirements rõ | LLM extract best-effort, caveat: "JD này hơi chung chung, mình suy luận skill từ description" |

## Không làm

- Không recommend course (Agent 8 Learning Path)
- Không đánh giá role có hợp user không (Agent 6 Career Advisor)
- Không trả salary / market trend (Agent 11, 12)
- Không update profile (Agent 3 Profile làm song song)
- Không chain sang agent khác (Manager B điều phối)
- Không extract skill từ job requirements ở runtime cho Mode A (pha extract offline đã làm xong, lưu sẵn ở `job_skills`)
- Không persist output / cache

## Quyết định đã chốt

| Vấn đề | Quyết định |
|---|---|
| Scope | So sánh skill user vs skill yêu cầu của 1 target (role hoặc job cụ thể) |
| 2 mode | A · By Role (aggregate DB) + B · By Job (LLM extract 1 JD) |
| Detect mode | Manager B classify (URL / job_id / text length) |
| Skill user hiện có | Đọc `user_profile` + recent messages, LLM tự reconcile |
| Mode A — nguồn skill yêu cầu | Internal-first (jobs DB) → Tavily fallback |
| Mode B — nguồn skill yêu cầu | LLM extract trực tiếp từ JD (job_id / URL / raw text) |
| Schema mới | Bảng `job_skills(job_id, skill_name, category)` |
| Normalize skill | Làm ngay ở pha extract (module data, không trong agent này) |
| Qdrant collection mới | `job_titles` — chỉ embed title |
| Retrieval Mode A | Hybrid: FTS5 (BM25 title) + Qdrant semantic (title-only) |
| Fusion | Reciprocal Rank Fusion |
| Verify Mode A | LLM batched call loại false positive |
| Fallback trigger Mode A | Số jobs có combined_score >= T mà < K → Tavily |
| Tavily Search config | Domain whitelist (linkedin/itviec/topcv/vietnamworks/topdev) + `include_raw_content=True` + query có phrasing |
| Tavily Extract Mode B | Dùng cho URL input |
| Priority Mode A | Frequency-based: must (≥50%) / should (25-50%) / nice (<25%) |
| Priority Mode B | LLM infer từ wording JD (bắt buộc / ưu tiên / còn lại) |
| Mode B evidence | Có (trích câu từ JD) |
| Cite sources | Có (link jobs từ DB hoặc URL Tavily / JD URL) |
| Output cache / persist | Không |
| Update profile từ Skill Gap | Không (Agent 3 làm song song) |
