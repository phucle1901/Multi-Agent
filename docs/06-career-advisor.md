# Agent 6 · Career Advisor

## Mục đích

Phân tích nghề phù hợp với profile user. Đưa ra **kết luận có cơ sở** (fit score, rationale, similar/top roles). Pure LLM reasoning, **không** dùng catalog file/DB/Qdrant.

Phân biệt với Agent 4 · Goal Setting:
- **Goal Setting**: coach đối thoại phản tư, KHÔNG recommend role cụ thể, chỉ save target_role vào profile.
- **Career Advisor**: analyst đưa ra role cụ thể với fit_score + rationale.

## Vị trí trong kiến trúc

Sub-agent của **Manager B · Tư vấn nghề nghiệp**. Gọi bởi Manager B (không trực tiếp từ Supervisor / UI).

## 3 Mode

| Mode | User intent | Tín hiệu | Input bắt buộc |
|---|---|---|---|
| **A · Validate** | "X có hợp không?" | có 1 role cụ thể trong message hoặc profile.target_role | `target_role` + ≥1 low-touch khác |
| **B · Recommend** | "ngành gì hợp em?" | không có role cụ thể; câu hỏi mở | MBTI **hoặc** Holland **hoặc** (edu + skills) |
| **C · Compare** | "X hay Y?" | ≥2 role + từ "vs"/"hay"/"so sánh" | ≥2 role từ message + ≥1 low-touch |

Manager B detect mode qua phân tích message + context profile rồi forward sang CA.

### Mode A · Validate target_role

Output gồm:
- `fit_score` (0-1)
- `fit_breakdown` — chia theo trục: education / skills / personality / preference
- `rationale` — tổng kết vì sao
- `similar_occupations` — 3-5 role gần kề + fit + why
- `next_suggestions`

### Mode B · Recommend top-K

Output gồm:
- `based_on` — liệt kê field profile dùng để recommend
- `top_recommendations` — 5 role + fit + why
- `next_suggestions` — "chọn 1 role → mình phân tích sâu (chuyển Mode A)"

KHÔNG đi sâu skill gap (Agent 7) hay course (Agent 8).

### Mode C · Compare roles

Output gồm:
- `roles_compared`
- `comparison_axes` — fit / skill overlap / growth trend HN / match preference / salary range chung
- `recommendation` — kết luận role nào lean hơn
- `next_suggestions`

## Pre-flight gating

### Nguyên tắc

1. **Luôn check profile** trước khi trả lời.
2. **Hỏi user** để bổ sung field thiếu; user **có quyền từ chối**.
3. **Phân loại field**:
   - **High-touch** (MBTI / Holland / Goal) → offer 2 lựa chọn: (a) qua nhóm A, (b) cung cấp inline
   - **Low-touch** (education / skills / current_role / target_role / preferences) → hỏi inline
4. Khi user từ chối / thiếu → trả lời **chỉ dựa trên info có**, **KHÔNG BỊA**.
5. **Max 2 turn ask** /session CA → tránh spam.

### Flow

```
1. CA nhận question → detect mode → list missing required fields
2. Nếu đủ required → trả lời FULL ngay
3. Nếu thiếu → enter ASK loop (max 2 turn):
   - High-touch missing → đề xuất 3 lựa chọn:
     (1) Qua nhóm A (làm test / khai vấn)
     (2) Cung cấp inline
     (3) Bỏ qua
   - Low-touch missing → hỏi inline (bỏ qua được)
4. User response:
   - Cung cấp → Agent 3 Profile extract & update song song, CA dùng tiếp
   - Chọn qua nhóm A → CA return redirect message, dừng phân tích
   - Bỏ qua / từ chối → mark skipped, không hỏi lại trong session
5. Sau ASK loop (đạt limit hoặc skip hết):
   → Trả lời với info HIỆN CÓ
   → KHÔNG fabricate
   → Caveat footer liệt kê field thiếu + cách bổ sung
```

### Ví dụ ask cho high-touch

> Để tư vấn chính xác hơn, mình cần biết hướng tính cách của bạn (MBTI/Holland). Bạn có thể:
> 1. Qua nhóm "Khám phá bản thân" làm test (~15 phút) — kết quả lưu vào profile, mình tư vấn dựa trên đó
> 2. Nếu đã có MBTI/Holland rồi, cho mình biết luôn
> 3. Bỏ qua, mình tư vấn với info hiện có

### Ví dụ ask cho low-touch

> Bạn có thể cho mình biết học ngành gì, skills hiện tại không? Hoặc bỏ qua cũng được, mình tư vấn với info đang có.

### Quy tắc "không bịa" — bắt buộc trong system prompt CA

> "CHỈ tham chiếu các field có trong profile. Nếu field thiếu: nói 'chưa biết' hoặc omit dimension đó. KHÔNG suy đoán MBTI từ cách nói chuyện. KHÔNG đoán salary nếu không có data. KHÔNG fabricate skills không được nêu."

## Input / Output

| | |
|---|---|
| **Input** | user message + `user_profile` + memory facts (filter `preference`) + ask_count tracker của session với CA |
| **Output (success)** | Structured dict cho Manager B render (xem 3 mode ở trên) |
| **Output (ask)** | `{action: "ask_user", high_touch?: bool, missing_field, message}` |
| **Output (redirect)** | `{action: "redirect_a", message}` |

## Data sources

| Nguồn | Dùng | Note |
|---|---|---|
| `user_profile` (SQL) | ✓ đọc | Core input |
| `memory_facts` (SQL) | ✓ đọc | Filter `preference` để personalize |
| LLM internal knowledge | ✓ | Phân tích nghề, fit, similar roles, growth trend |
| Catalog file / SQL `occupations` | ✗ | KHÔNG — pure LLM reasoning |
| Qdrant `occupations` | ✗ | KHÔNG — overview giới hạn Qdrant cho jobs |
| Tavily | ✗ | KHÔNG — LLM đủ; salary/market chi tiết có Agent 11, 12 |

## Schema impact

**KHÔNG tạo bảng SQL mới.**  
**KHÔNG tạo Qdrant collection mới.**  
CA pure compute từ `user_profile` + `memory_facts`.

## Không làm

- Không recommend course (Agent 8 Learning Path)
- Không tính skill gap chi tiết (Agent 7 Skill Gap)
- Không trả salary cụ thể (Agent 12 Salary)
- Không trả market trend chi tiết (Agent 11 Market Insight)
- Không update profile trực tiếp (Agent 3 Profile làm song song)
- Không chain sang agent khác (Manager B điều phối)
- Không dùng Tavily
- Không fabricate field thiếu

## Quyết định đã chốt

| Vấn đề | Quyết định |
|---|---|
| Mode | 3: validate / recommend / compare |
| Catalog nghề | KHÔNG — pure LLM reasoning |
| Gating | Theo required field của mode, không tier cứng |
| High-touch fields | MBTI / Holland / Goal → offer 3 path (qua A / inline / bỏ qua) |
| Low-touch fields | edu / skills / current_role / target_role / pref → ask inline (bỏ qua được) |
| User có quyền từ chối | ✓ — mark skipped, không hỏi lại |
| User chọn qua A | CA return redirect, Manager B dừng phân tích, user quay lại sau |
| Ask limit | Max 2 turn /session CA |
| Sau ask loop nếu vẫn thiếu | Trả lời với info CÓ; **KHÔNG BỊA**; caveat liệt kê field thiếu |
| Profile update | Agent 3 Profile làm song song; CA chỉ đọc + dùng message real-time |
| Web search | Không dùng Tavily |
