# Agent 8 · Learning Path

## Mục đích

Thiết kế **lộ trình học** cá nhân hoá để fill skill gap. Nhận `missing_skills` (từ Skill Gap, từ user gõ trực tiếp, hoặc infer từ profile) → đề xuất course cụ thể cho từng skill + sắp xếp thứ tự + plan theo tuần.

## Vị trí trong kiến trúc

Sub-agent của **Manager B · Tư vấn nghề nghiệp**. Cuối chain `Career Advisor → Skill Gap → Learning Path`. Cũng có thể gọi standalone (user hỏi thẳng course cho 1 skill).

## Input modes

| Mode | Trigger | Input |
|---|---|---|
| **Chained** | Sau Skill Gap trong chain Manager B | `missing_skills` từ Skill Gap (đã có category + priority) |
| **Standalone** | User hỏi trực tiếp về course | `skill_list` (text từ message) + `user_profile` |

LP đọc thêm: `user_profile` (level, target_role, years_exp), recent messages.

## Input / Output

| | |
|---|---|
| **Input** | `skill_list` (chained: từ Skill Gap; standalone: parse message) + `user_profile` |
| **Output** | Lộ trình học chi tiết (xem cấu trúc bên dưới) |

### Cấu trúc output

```json
{
  "mode": "chained",                          // "chained" | "standalone"
  "user_level": "beginner",                   // LLM infer từ profile
  "total_duration_weeks": 16,
  "skills_to_learn": [
    {
      "skill": "SQL",
      "priority": "must-have",                // pass-through từ Skill Gap (hoặc default 'must' khi standalone)
      "category": "hard",
      "estimated_weeks": 4,
      "order": 1,
      "rationale": "Foundation cho data role, học trước Python/Tableau",
      "courses": [
        {
          "title": "SQL for Data Analysis",
          "platform": "Coursera",
          "url": "...",
          "duration": "~20h",
          "level": "beginner",
          "price": "free / paid",
          "language": "EN",
          "why_recommended": "Top rating, university-backed"
        }
        // 2-3 course/skill
      ]
    }
  ],
  "weekly_plan": [
    {"week_range": "1-4",   "focus": "SQL",     "milestone": "Hoàn thành course SQL Coursera + 10 bài luyện trên LeetCode/HackerRank"},
    {"week_range": "5-10",  "focus": "Python",  "milestone": "..."},
    {"week_range": "11-16", "focus": "Tableau", "milestone": "Build 1 dashboard demo"}
  ],
  "caveat": null
}
```

## Data sources

| Nguồn | Vai trò | Khi dùng |
|---|---|---|
| `user_profile` (SQL) | Level / years_exp / target_role / current_skills | Luôn |
| Skill Gap output | `missing_skills` với priority + category | Khi chained |
| Recent messages | Bắt skill / sở thích user vừa nhắc | Luôn |
| **Tavily Search** | Tìm course thực tế từ Coursera/Udemy/edX/... | Luôn (primary, không có fallback) |

## Flow xử lý

```
1. LP nhận skill_list + user context
   │
2. Infer user_level từ profile (LLM reason):
   │  - years_experience, current_role, target_role
   │  - current skills familiarity (đã có skill cơ bản → intermediate course)
   │  - profile rỗng → assume beginner + caveat
   │
3. Sequencing: LLM reason về dependency
   │  - Foundation skill trước (vd SQL trước Pandas trước Tableau)
   │  - Output order index 1, 2, 3...
   │
4. Per-skill course search — Tavily (EN query):
   │  Loop từng skill:
   │    query = '"{skill_name}" course tutorial {level} 2026'
   │    Tavily search với domain whitelist (xem Tavily config)
   │    LLM filter 2-3 course best per skill
   │    Extract: title, platform, url, duration, level, price, language
   │
5. Estimate weeks per skill (LLM):
   │  - Dựa course duration + skill complexity + user_level
   │  - Tổng total_duration_weeks
   │
6. Build weekly_plan:
   │  - Group theo order + estimated_weeks
   │  - Mỗi block có milestone cụ thể (course xong + bài luyện tập)
   │
7. Output structured JSON cho Manager B render
```

## Tavily config

```python
TavilySearchResults(
    max_results=10,
    search_depth="advanced",
    include_raw_content=False,                 # snippet đủ cho course discovery
    include_domains=[
        "coursera.org",
        "udemy.com",
        "edx.org",
        "youtube.com",
        "freecodecamp.org",
        "datacamp.com",
        "codecademy.com",
    ],
)

query = f'"{skill_name}" course tutorial {level} 2026'
# vd: '"SQL" course tutorial beginner 2026'
```

**Query EN thuần** — để ra course tiếng Anh chất lượng cao (Coursera/Udemy EN edition). User đã chốt khoá tiếng Anh ổn hơn cho skill technical.

Nếu skill name tiếng Việt (vd "Quản lý dự án") → LP translate sang EN trước khi query ("Project Management").

## Schema impact

**KHÔNG tạo bảng mới.**
**KHÔNG tạo Qdrant collection mới.**
**KHÔNG cache Tavily result.**

LP pure compute, stateless theo nguyên tắc overview ("Không persist output của agent stateless: Mock Interview, Learning Path, Negotiation...").

## Tham số

| Param | Mặc định | Ý nghĩa |
|---|---|---|
| `courses_per_skill` | 2-3 | Số course đề xuất / skill |
| `max_skills_in_path` | 5-7 | Limit skill trong lộ trình (case quá nhiều missing) |
| `tavily_max_results` | 10 | Per skill query |

## Edge cases

| Case | Xử lý |
|---|---|
| Skill quá rộng (vd "AI", "Lập trình") | Ask back: "Bạn muốn focus AI gì? ML / NLP / CV?" — Manager B forward |
| Skill rare/niche (vd "Cobol", "Solidity") | Tavily ít result → caveat "skill này hiếm course, đây là kết quả tốt nhất" |
| Quá nhiều skill (>7 missing) | Limit top 5-7 ưu tiên cao nhất (must > should > nice), note "skill khác học sau" |
| Profile + message đều rỗng context | Assume beginner + general path + caveat |
| Tavily trả 0 result cho 1 skill | Skill vẫn liệt kê trong `skills_to_learn`, `courses: []` + note "không tìm được, gợi ý tự search Coursera/Udemy" |
| Standalone không có context priority | Default tất cả skill = must-have, LP vẫn sequence theo dependency |
| Skill name tiếng Việt | LLM translate sang EN trước khi Tavily query |

## Không làm

- Không đánh giá role có hợp user không (Agent 6 Career Advisor)
- Không tính skill gap chi tiết (Agent 7 Skill Gap)
- Không trả salary / market trend (Agent 11, 12)
- Không update profile (Agent 3 Profile làm song song nếu user nhắc skill mới)
- Không chain sang agent khác (Manager B điều phối)
- Không persist output / cache Tavily result
- Không dùng internal DB jobs (LP focus vào course, không vào jobs)
- Không build dependency graph cứng (LLM tự reason)
- Không hard-code level mapping (LLM tự reason từ profile)

## Quyết định đã chốt

| Vấn đề | Quyết định |
|---|---|
| Scope | Thiết kế lộ trình học cá nhân hoá fill skill gap |
| Input | 2 mode: chained (từ Skill Gap) + standalone (user gõ thẳng) |
| Output | List course per skill + weekly_plan có thứ tự + milestone |
| Sequencing | LLM reason về dependency (không build graph cứng) |
| Số course/skill | 2-3 |
| Data source | Tavily Search (primary, không có fallback) |
| Tavily query language | EN thuần (để ra course tiếng Anh chất lượng cao) |
| Skill name tiếng Việt | LLM translate sang EN trước query |
| Tavily domain whitelist | coursera.org, udemy.com, edx.org, youtube.com, freecodecamp.org, datacamp.com, codecademy.com |
| Level matching | LLM reason từ profile (years_exp, current_role, current_skills) |
| Standalone mode level | Infer từ profile; profile rỗng → beginner + caveat |
| Max skill trong path | 5-7 (limit khi quá nhiều missing) |
| Persist / cache | Không (stateless theo overview) |
| Schema mới | Không |
| Qdrant collection mới | Không |
