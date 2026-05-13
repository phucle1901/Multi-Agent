# Agent 9 · Job Search

## Mục đích

Tìm jobs phù hợp với yêu cầu user (role, location, salary, level, work_mode, industry...). Trả về list jobs match + link. **Không** apply qua hệ thống.

Đây là agent cốt lõi của topic đồ án "tư vấn nghề nghiệp & phân tích việc làm tại Hà Nội".

## Vị trí trong kiến trúc

Sub-agent của **Manager C · Tìm việc làm**. Gọi bởi Manager C (không trực tiếp từ Supervisor / UI).

## Modes

| Mode | Trigger | Input đặc trưng |
|---|---|---|
| **Fresh search** | Query mới về việc làm | user_message + user_profile |
| **Refine** | User narrow/đổi constraint từ search trước (vd "lọc thêm lương 20-30tr") | user_message + previous `filter` từ `messages.metadata` |

Manager C detect refine qua keyword ("lọc thêm", "thêm điều kiện", "trong list trên", "đổi sang...") + LLM classify. Khi refine → merge filter cũ với constraint mới → coi như fresh search với filter mở rộng. **Không** có code path "refine narrow" riêng — đơn giản hoá.

## Input / Output

| | |
|---|---|
| **Input** | `user_message` + `user_profile` + (optional) `previous_filter` từ `messages.metadata.last_search.filter` |
| **Output (success)** | Structured dict (xem mục Output structure) |
| **Output (ask)** | Nếu thiếu `role` hoặc role quá rộng → ask back |

### Output structure

```json
{
  "filter_used": {
    "role": "AI Engineer",
    "location": "Hà Nội",
    "level": "fresher",
    "salary_min": null,
    "salary_max": null,
    "work_mode": null,
    "experience_max": 1,
    "industry": null
  },
  "filter_inferred_from_profile": ["level"],
  "total_found": 25,
  "total_after_verify": 12,
  "jobs": [
    {
      "source": "internal",                       // "internal" | "tavily"
      "rank": 1,
      "job_id": 123,                              // null nếu source=tavily
      "title": "AI Engineer - Fresh Graduate",
      "company": "FPT Software",
      "location": "Cầu Giấy, Hà Nội",
      "salary_raw": "15-20 triệu",
      "level": "Nhân viên",
      "work_mode": "hybrid",
      "url": "https://...",
      "match_score": 0.92,
      "match_reasons": ["title match AI Engineer", "level match fresher", "location HN"],
      "summary": "Tóm tắt ngắn JD 2-3 câu"
    }
  ],
  "refine_suggestions": "Bạn muốn lọc thêm theo lương / công ty / phường không?",
  "caveat": null
}
```

`filter_inferred_from_profile` = list field lấy default từ profile (transparency cho user biết "à, hệ thống tự suy ra level từ profile").

## Data sources

| Nguồn | Vai trò |
|---|---|
| `user_profile` (SQL) | Default cho field user không nhắc |
| Recent messages (`messages.metadata.last_search`) | Lấy `filter` cũ khi refine |
| `jobs`, `companies`, `phuongs`, `loai_jobs`, `job_phuong`, `job_loai_jobs` | Core DB jobs |
| `job_skills` | Soft match rerank theo skill |
| `jobs_fts` (FTS5 / tsvector) | BM25 search title |
| Qdrant collection `job_titles` | Semantic search title-only |
| **Tavily Search** | Live search web song song |

## Flow xử lý

```
1. PARSE QUERY (LLM):
   Extract structured filter từ user_message:
     - role, location, salary, level, work_mode, experience, industry
   Profile làm default cho field user không nhắc
   Track filter_inferred_from_profile

2. MERGE FILTER (nếu refine):
   Nếu Manager C detect refine → đọc previous_filter từ messages.metadata
   Merge với constraint mới user vừa nói

3. ASK BACK nếu:
   - Thiếu role hoàn toàn (cả message lẫn profile.target_role không có)
   - Role quá rộng (vd "việc làm IT", "việc gì cũng được")

4. PARALLEL RETRIEVAL:
   
   Branch A · Internal DB:
     Stage 1 — SQL filter cứng (HARD constraints):
       WHERE deadline >= today
         AND (salary_min >= X OR salary_min IS NULL)
         AND (salary_max <= Y OR salary_max IS NULL)
         AND experience_years <= max_exp
         AND work_type = ... (nếu có)
         AND work_mode_extracted IN (...)
         AND phuong_id IN (selected_phuongs)  via JOIN job_phuong
     
     Stage 2 — Hybrid soft match trên kết quả Stage 1:
       FTS5 BM25 trên title → score_fts
       Qdrant semantic trên job_titles → score_qdrant
       RRF: combined = 1/(60+rank_fts) + 1/(60+rank_qdrant)
     
     Stage 3 — Rerank bổ sung:
       Bonus jobs có job_skills match user.hard_skills
       Bonus jobs có loai_job match user query industry
     
     → Top 30 candidates
   
   Branch B · Tavily Search:
     query = '"{role}" "Hà Nội" ("tuyển dụng" OR "việc làm" OR "hiring") {level_keyword} 2026'
     include_domains: linkedin, itviec, topcv, vietnamworks, topdev, careerlink, careerbuilder
     include_raw_content=True
     max_results=10
     
     LLM extract structured info từ raw_content:
       → {title, company, location, salary, level, work_mode, url, summary}
     
     → Top 10 candidates

5. LLM VERIFIER (batched, 1 LLM call):
   Pass 30 candidates DB + 10 candidates Tavily vào 1 prompt:
     "User cần role X level Y location Z. Job nào THỰC SỰ match?"
   Output: indices passed
   Loại false positive (Business Analyst lọt vào query Data Analyst, etc.)

6. DEDUP:
   URL exact match (jobs trên Tavily có thể trùng DB topcv)
   Ưu tiên giữ source=internal (có structured data đầy đủ)

7. SORT:
   match_score DESC (primary)
   salary_min IS NULL ASC (secondary — jobs có số xếp trước "Thoả thuận")

8. OUTPUT top 10 + refine_suggestions

9. STORE state (chỉ filter, không tavily_snapshot):
   messages.metadata = {
     "last_search": {"filter": {...filter_used}}
   }
```

## Hard / Soft constraints

| Field | Loại | Cách filter |
|---|---|---|
| `salary` | Hard | SQL `salary_min`/`salary_max`. Include NULL ("Thoả thuận"), sort sau |
| `location` (phường) | Hard | SQL JOIN `job_phuong`. Jobs có ≥80 phường = "all HN" → match mọi query HN |
| **level** | Hard, qua proxy `experience_years` | fresher (≤1), junior (1-3), middle (3-5), senior (≥5). KHÔNG dùng cột `level` text thô |
| `experience_years` (max) | Hard | SQL |
| `deadline >= today` | Hard | SQL — loại job hết hạn |
| `work_type` | Hard nếu user rõ | SQL exact match ("Toàn thời gian"/"Bán thời gian"/"Thực tập") |
| `work_mode_extracted` | Hard | SQL ENUM. Logic: user nói "remote" → `= 'remote'`; "hybrid" → `IN ('hybrid','remote')`; "onsite" → `IN ('onsite','unknown')` |
| `role / title` | Soft | FTS5 BM25 + Qdrant `job_titles` |
| `skill` | Soft rerank | JOIN `job_skills` — bonus nếu user có skill match |
| `industry` | Soft rerank | `loai_jobs` + `company_field` |

## Tavily config

```python
TavilySearchResults(
    max_results=10,
    search_depth="advanced",
    include_raw_content=True,
    include_domains=[
        "linkedin.com", "vn.linkedin.com",
        "itviec.com",
        "topcv.vn",
        "vietnamworks.com",
        "topdev.vn",
        "careerlink.vn",
        "careerbuilder.vn",
    ],
)

query = f'"{role}" "Hà Nội" ("tuyển dụng" OR "việc làm" OR "hiring") {level_keyword} 2026'
```

Sau Tavily → LLM extract structured info (title, company, location, salary, level, url, summary).

## State management (refine)

- Chỉ lưu `filter` vào `messages.metadata.last_search` của message assistant
- Manager C đọc recent assistant message → lấy `filter` → merge với constraint mới user vừa nói → gọi JS với merged filter
- **KHÔNG** lưu `tavily_snapshot` → mỗi refine = fresh Tavily call
- Trade-off: Tavily cost cao hơn 1 chút, nhưng đơn giản logic, luôn fresh data

### Scan rule — đọc filter cũ

**Thống nhất 1 query cho mọi mode** (xem [0.0-modes-and-communication.md](./0.0-modes-and-communication.md)). Manager C / Job Search KHÔNG cần biết đang ở Mode 0 hay Mode 3 — luôn filter `handled_by = 'manager_c'`:

```sql
SELECT metadata->'last_search'->'filter'
FROM messages
WHERE conversation_id = ?
  AND role = 'assistant'
  AND metadata->>'handled_by' = 'manager_c'
  AND metadata->'last_search' IS NOT NULL
ORDER BY created_at DESC
LIMIT 1;
```

- **Mode 0**: filter bỏ qua turn của Manager khác đan xen → tìm đúng `last_search` gần nhất của Manager C.
- **Mode 3 (Locked C)**: mọi assistant message đều `handled_by = manager_c` → filter trả full → query đúng tự nhiên.

```json
// messages.metadata sau search:
{
  "last_search": {
    "filter": {
      "role": "AI Engineer",
      "location": "Hà Nội",
      "level": "fresher",
      "salary_min": null,
      "salary_max": null,
      "work_mode": null,
      "experience_max": 1,
      "industry": null
    }
  }
}
```

## Tham số

| Param | Mặc định | Ý nghĩa |
|---|---|---|
| `top_n_db_after_soft` | 30 | Top jobs DB sau RRF fusion |
| `tavily_max_results` | 10 | Per query |
| `llm_verifier_batch_size` | 40 | Tổng candidates pass vào verifier (30 DB + 10 Tavily) |
| `max_jobs_displayed` | 10 | Top trả về user |
| `score_threshold T` | TBD | Min RRF score (chỉnh sau test) |

## Edge cases

| Case | Xử lý |
|---|---|
| Thiếu role hoàn toàn | Ask back: "Bạn muốn tìm role nào?" |
| Role quá rộng ("việc làm IT") | Ask back: "Cụ thể role nào? SWE / Data / DevOps...?" |
| 0 jobs sau verifier | Empty + caveat "Không tìm thấy job match, có thể nới constraint X Y" |
| DB 0 jobs (role niche) | Dựa hẳn vào Tavily, caveat "DB không có data, kết quả từ web" |
| Tavily timeout / fail | Internal-only + caveat "Web search hiện không khả dụng" |
| Job hết deadline | SQL filter cứng `deadline >= today` |
| Salary "Thoả thuận" (NULL) | Include trong kết quả, sort sau jobs có số. Caveat: "X jobs lương 'Thoả thuận' hiển thị ở cuối" |
| Profile rỗng | Search rộng (không default filter) + caveat |
| Refine — user đổi cả role | Merge filter, role mới ghi đè role cũ → fresh search |

## Schema impact

Schema đã ghi đầy đủ ở [`design_data.md`](./design_data.md). Job Search dùng:

- **Bảng**: `jobs`, `companies`, `phuongs`, `loai_jobs`, `job_phuong`, `job_loai_jobs`, `job_skills`, `jobs_fts`
- **Cột mới (đã note)**: `jobs.source`, `jobs.work_mode_extracted`, `jobs.work_mode_extracted_at`, `jobs.skills_extracted_at`
- **Qdrant**: collection mới `job_titles`
- **Pipeline data module**: skill extract + work_mode extract + indexing job_titles

## Không làm

- Không apply job thay user (chỉ trả link)
- Không cross-call agent khác
- Không update profile (Agent 3 song song)
- Không persist output (state qua `messages.metadata`, không bảng cache)
- Không lưu lịch sử search dài hạn
- Không phân tích salary/market trend chi tiết (Agent 11, 12)
- Không xem chi tiết công ty (Agent 10 · Company)

## Quyết định đã chốt

| Vấn đề | Quyết định |
|---|---|
| Scope | Tìm jobs match user req, trả link |
| Data sources | Hybrid live: internal DB + Tavily song song |
| Retrieval | Hybrid SQL filter (hard) + FTS5/Qdrant (soft) |
| Hard constraints | salary, location, experience_years (proxy cho level), deadline, work_type, work_mode_extracted |
| Soft match | role/title (FTS5+Qdrant title-only), skill rerank, industry rerank |
| Level handling | Dùng `experience_years` proxy, KHÔNG dùng cột `level` text thô |
| Work mode | Cột `work_mode_extracted` ENUM, extract offline 2-pha (note ở design_data.md) |
| Source multi-source | Cột `source` ENUM trong `jobs` (note ở design_data.md) |
| LLM Verifier | Batched call (1 LLM cho 30-40 jobs) |
| Tavily config | Domain whitelist + raw_content + query "Hà Nội" + năm |
| Dedup | URL exact match, ưu tiên giữ internal |
| Salary "Thoả thuận" | Include với NULL, sort sau jobs có số, caveat |
| Sort order | match_score DESC, salary_min IS NULL ASC |
| Display limit | Top 10 + refine_suggestions |
| Ask back | Bắt buộc role; optional khác (search rộng + suggest refine) |
| Refine state lưu ở | `messages.metadata.last_search.filter` (Option F1 — không Redis, không snapshot) |
| Refine xử lý | Tất cả refine = fresh search với merged filter (Tavily luôn gọi lại) |
| Trade-off | Tavily cost cao hơn 1 chút vs logic đơn giản + data fresh — chọn đơn giản |
