# Agent 10 · Company

## Mục đích

Cung cấp thông tin về **1 hoặc nhiều công ty cụ thể** để user research trước khi apply / onboard: văn hóa, môi trường, phúc lợi, review nhân viên, tin tức gần đây, profile cơ bản, tech stack, cơ hội phát triển, quy trình tuyển dụng.

**Không** giúp tìm việc (Job Search xử lý). **Không** phân tích landscape ngành (Market Insight xử lý).

## Vị trí trong kiến trúc

Sub-agent của **Manager C · Tìm việc làm**. Gọi bởi Manager C, không trực tiếp từ Supervisor / UI.

## Invariant đầu vào

Input từ Manager C **luôn có ≥1 tên công ty cụ thể**. Manager C gate trước khi dispatch:

- Câu research công ty không có tên cụ thể → Manager C ask-back **mô tả scope nhóm C** để user clarify, **không cross-suggest** group khác (chưa chắc Market Insight cover được câu — có thể off-scope project hoàn toàn).
- Quy tắc cross-suggest **không generalize** cho cả 6 Manager. Mỗi Manager quyết định riêng tuỳ scope agent đích rõ ràng hay không — bàn cụ thể khi discuss từng Manager.

## Input / Output

| | |
|---|---|
| **Input** | `user_message` + `company_names: list[str]` + `mode: "single" \| "multi" \| "compare"` (Manager C classify) |
| **Output** | Structured dict (xem mục Output structure) |

### Output structure

```json
{
  "companies_queried": ["FPT Software", "Viettel"],
  "mode": "single" | "multi" | "compare",
  "companies": [
    {
      "name": "FPT Software",
      "found": true,
      "info": {
        "basic_profile": {
          "industry": "...",
          "size": "...",
          "founded": 1999,
          "headquarters": "...",
          "website": "...",
          "ceo": "..."
        },
        "culture": "...",
        "benefits": "...",
        "reviews": {
          "rating_summary": "3.8/5 trên ITviec (~400 review)",
          "pros": ["..."],
          "cons": ["..."]
        },
        "interview_process": "...",
        "recent_news": [
          {"date": "2026-04", "headline": "...", "url": "..."}
        ],
        "tech_stack": ["..."],
        "career_growth": "..."
      },
      "sources": [
        {"url": "...", "used_for": ["reviews", "benefits"]}
      ],
      "clarify": null,
      "caveat": null
    }
  ],
  "comparison_summary": null,
  "error": null,
  "caveat": null
}
```

- Mọi `info.*` field **nullable** — Tavily không có signal → null, **không bịa**.
- `clarify` chỉ fill khi tên cty mơ hồ → entry KHÔNG fire Tavily cho cty đó.
- `comparison_summary` chỉ fill khi `mode = "compare"`.
- `error` ở top-level chỉ fill khi Tavily down toàn bộ.

## Cap số công ty per turn

| Mode | Cap |
|---|---|
| `single` | 1 |
| `multi` (hỏi nhiều cty rời rạc) | 3 |
| `compare` (yêu cầu so sánh) | 3 |

Vượt cap → research 3 cty đầu + global caveat "Mình research 3 cty đầu, còn lại hỏi tiếp sau".

## Data sources

| Nguồn | Vai trò |
|---|---|
| **Tavily Search** | DUY NHẤT — 100% content từ web |
| `user_profile` | KHÔNG đọc — pure research, Manager C personalize sau |
| `memory_facts` | KHÔNG đọc — như trên |
| SQL bảng `companies` | KHÔNG đọc — table phục vụ Job Search filter, không trùng scope Company info |

## Flow xử lý

```
1. CLARIFY check:
   Tên cty mơ hồ (vd "FPT" → Software/Telecom/Retail)
   → return `clarify` field với candidates list, KHÔNG fire Tavily cho cty đó

2. BUILD 3 QUERIES per cty (tiếng Việt mặc định):
   - Overview: '"{name}" giới thiệu công ty quy mô lĩnh vực phúc lợi'
   - Review:   '"{name}" review nhân viên đánh giá làm việc'
   - News:     '"{name}" tin tức mới nhất'

   Tavily config:
     search_depth        = "advanced"
     include_raw_content = True
     max_results         = 10
     exclude_domains     = ["facebook.com", "youtube.com", "tiktok.com"]
     timeout             = 20s per call

3. FIRE PARALLEL:
   Toàn bộ Tavily call (N cty × 3 query) fire song song qua asyncio.gather.
   Max call/turn = 3 cty × 3 query = 9.

4. LANG FALLBACK (chỉ cho Overview):
   Nếu Overview VN trả < 3 raw_content có signal
   → fire EN equivalent query → merge raw_content
   Review + News giữ VN, không fallback.

5. ERROR HANDLING (xem mục Edge cases).

6. LLM EXTRACT (1 call gộp per company):
   Đẩy toàn bộ raw_content của 3 query của 1 cty → 1 prompt
   → LLM extract full card JSON match schema
   - Cross-reference giữa nguồn (review + overview cùng nói 1 thứ → confidence cao)
   - LLM emphasize field liên quan tới user_message (vd user hỏi "lương" → benefits/reviews rich hơn,
     news có thể null nếu raw không signal cho câu hỏi)
   - News bắt buộc có `date` extract được — không date → drop khỏi recent_news[]
   - Field nào Tavily không có signal → null (KHÔNG bịa)

7. ASSEMBLE OUTPUT:
   companies[] + mode + comparison_summary (nếu mode=compare) + global caveat (nếu có)
```

## Tham số

| Param | Giá trị |
|---|---|
| `max_companies_per_turn` | 3 |
| `tavily_timeout_per_call` | 20s |
| `tavily_max_results_per_query` | 10 |
| `tavily_search_depth` | advanced |
| `tavily_include_raw_content` | True |
| `tavily_exclude_domains` | [facebook.com, youtube.com, tiktok.com] |
| `tavily_retry_count` | 1 (backoff 1s) |
| `query_language` | VN-first + EN-fallback cho Overview khi VN <3 signal |
| `parallelism` | asyncio.gather (no semaphore) |

## State management

**Stateless hoàn toàn.** Không cache, không log filter, không lưu output vào `messages.metadata`.

Khi user follow-up cùng cty turn sau → **re-fire fresh** đầy đủ 3 query (đồng nhất pattern với Job Search refine — "đơn giản + data fresh").

## Edge cases

| Case | Xử lý |
|---|---|
| Tên cty mơ hồ (FPT → Software/Telecom/Retail) | `clarify` field với candidates, không fire Tavily cho cty đó |
| Tên sai chính tả ("Vietttel") | Tavily tolerant, vẫn search; caveat per cty nếu confidence thấp |
| Cty không nổi tiếng, 0 result chất lượng | `found: false` + caveat "Không tìm thấy info chất lượng — có thể cty nhỏ/mới" |
| >3 cty cùng lúc | Cap 3 đầu + global caveat |
| News cũ (>24 tháng) | Vẫn giữ với date; Manager C visually mark "(cũ — 2022)" khi synthesize |
| News không extract được date | Drop khỏi `recent_news[]` |
| MNC (Google VN, MS VN…) | EN fallback fire khi VN Overview <3 signal |
| 1 Tavily query fail (3 query của 1 cty) | Retry 1 lần với backoff 1s → partial nếu vẫn fail + caveat per cty |
| All 3 query fail cho 1 cty | `found: false` + caveat per cty "Tavily không phản hồi cho cty này" |
| Toàn bộ Tavily down | Trả `{error: "tavily_unavailable", message}`, Manager C surface message |
| LLM extract trả JSON malformed | Retry LLM 1 lần với strict mode → nếu vẫn fail set `caveat` per cty |

## Schema impact

**Không thêm gì vào SQL / Qdrant / static file.** Chỉ thêm dòng mapping vào [`design_data.md`](./design_data.md) mục V.

## Không làm

- Không đọc `user_profile` / `memory_facts` (personalize là việc Manager C)
- Không đọc bảng `companies` SQL (Job Search dùng table này)
- Không cross-call agent khác
- Không persist gì
- Không truy vấn jobs của công ty (Job Search việc đó)
- Không phân tích ngành / market trend (Market Insight việc đó)
- Không giúp apply / liên hệ HR
- Không lưu lịch sử research của user

## Quyết định đã chốt

| Vấn đề | Quyết định |
|---|---|
| Scope | Research info về công ty cụ thể, KHÔNG tìm việc |
| Data source | Tavily 100%, không đụng DB / Qdrant / profile / memory |
| Input invariant | Luôn có ≥1 tên cty (Manager C gate trước) |
| Cap số cty | single=1, multi=3, compare=3 |
| Số query per cty | 3 (Overview + Review + News) — always fire, không scope theo intent |
| LLM tự lọc info relevant | Có — LLM extract emphasize field liên quan tới user_message |
| Mode | `single` / `multi` / `compare` — Manager C classify, agent không tự classify |
| Domain | Không whitelist; exclude noise (facebook/youtube/tiktok) |
| Ngôn ngữ | VN-first + EN-fallback cho Overview |
| Recency | Không hard-filter; news cũ vẫn giữ với date, Manager C mark khi synthesize |
| Parallelism | asyncio.gather toàn bộ (max 9 call) |
| Timeout | 20s per Tavily call |
| Retry Tavily | 1 lần backoff 1s |
| LLM extract | 1 call gộp per cty, raw_content từ 3 query |
| `found: false` | Vẫn giữ entry trong companies[], có caveat per cty |
| State | Stateless 100%, fresh mỗi turn |
| Cross-suggest rule | Case-by-case per Manager, KHÔNG generalize |
| Schema impact | Không SQL/Qdrant/static; chỉ thêm dòng mapping |
