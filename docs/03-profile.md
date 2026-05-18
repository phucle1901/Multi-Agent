# Agent 3 · Profile

## Mục đích

Slot-fill bảng `user_profile` từ messages — chứa **structured fields** dài hạn, dùng cho **logic filter / match** ở các agent nghiệp vụ (Skill Gap, Job Search, Salary, Career Advisor...).

## Vị trí trong kiến trúc

Hạ tầng. Chạy **mỗi turn**, **song song** với luồng chính và song song với Agent 2 · Memory.

```
User gửi input ──┬─► Supervisor → Manager → sub-agent → response   (luồng chính)
                 ├─► Agent 2 · Memory     (song song)
                 └─► Agent 3 · Profile    (song song)
```

Profile mới có hiệu lực ở turn **kế tiếp**, không trong cùng turn (chấp nhận trade-off, đổi lấy latency thấp).

## Input / Output

| | |
|---|---|
| **Input** | user message vừa nhận + N message gần nhất từ conversation + current `user_profile` row |
| **Output** | UPDATE các slot có giá trị mới / thay đổi trên `user_profile` |

## Write logic (mỗi turn)

```
1. Đọc user_profile hiện tại
2. LLM nhận: (current profile) + (recent messages) + (user message mới)
3. LLM output: dict các slot cần update (chỉ slot có context rõ ràng, không thuộc blacklist)
   vd: {"major": "CNTT", "work_mode": "remote"}
4. UPDATE user_profile SET ... WHERE user_id = X
```

**Slot không nhắc → giữ nguyên.** KHÔNG reset về NULL khi LLM không thấy thông tin trong turn này.

### Field Profile KHÔNG được ghi (blacklist)

Các field sau Profile **KHÔNG bao giờ** ghi, kể cả khi user gõ rõ ràng:

- `goal_type`, `target_role`, `target_salary_min_vnd`, `target_salary_max_vnd`, `target_date`
- `mbti_type`, `holland_code`
- `mbti_completed_at`, `holland_completed_at`

User nói "em là INTJ" / "em muốn DA 25tr" trong chat → Profile **bỏ qua**. Signal nằm trong message text của turn đó (sub-agent đọc `recent_messages` thấy được trong cùng turn), nhưng KHÔNG persist vào `user_profile`. Memory cũng không capture các mention này — đây là scope của Goal Setting / Assessment.

### Strict extraction rule — cho slot KHÔNG nằm trong blacklist

Prompt phải kỹ để tránh ghi đè sai từ câu nói qua loa:

**Khi nào EXTRACT (write):**
- User declarative về bản thân: "em là sinh viên CNTT" → `major`, `employment_status`
- User explicit decision / change: "em chuyển sang làm remote" → `work_mode`
- User trả lời trực tiếp câu hỏi profile từ agent: Manager hỏi "lương hiện tại?" → "15tr" → `current_salary_vnd_month`

**Khi nào KHÔNG extract (skip slot đó):**
- Bình luận / đánh giá: "remote nghe sướng nhỉ" → KHÔNG ghi
- Câu hỏi: "lương DA bao nhiêu?" → KHÔNG ghi
- Hypothetical: "nếu em làm freelance thì sao?" → KHÔNG ghi
- Nói về người khác: "bạn em làm IT" → KHÔNG ghi
- Mơ hồ field hoặc value → KHÔNG ghi (thà miss còn hơn ghi sai)

**Rule chung:** slot chỉ ghi khi LLM xác định **cả field name lẫn value đều rõ ràng** VÀ **user đang khẳng định về bản thân mình**. Mơ hồ một trong hai → bỏ qua slot đó.

## Schema — bảng `user_profile`

Xem [design_data.md#user_profile](./design_data.md#user_profile).

Tất cả slot nullable — Profile fill dần qua hội thoại, không bắt buộc đầy đủ.

## Read API cho agent khác

```python
get_profile(user_id: int) -> Profile   # single SELECT, 1 row
```

### Helper format-cho-prompt

```python
get_profile_as_prompt_block(user_id) -> str
# →
# ## Profile user
# - Học vấn: Cử nhân CNTT, ĐH Bách Khoa, 2024 (GPA 3.4)
# - Hiện tại: Sinh viên, 0 năm KN
# - Skills: Python, SQL (cơ bản)
# - Mục tiêu: Data Analyst, 15-25tr/tháng, trong 6 tháng, tại Cầu Giấy
# - MBTI: INTJ · Holland: RIA
# - Pref: remote, startup, fintech
```

## Write API (chỉ Agent 3 dùng nội bộ)

```python
update_profile(user_id, slots: dict)
# slots: {column_name: new_value, ...}
# Chỉ update các slot có trong dict; slot khác giữ nguyên.
```

## Ranh giới với Memory

| Loại | Đi đâu | Lý do |
|---|---|---|
| Học vấn / kinh nghiệm / skill list / goal / MBTI / Holland | **Profile** | Structured, query bằng SQL |
| Job preference structured (work_mode, size, industry) | **Profile** | Filter job dùng SQL |
| Preference mềm / qualitative không có slot tương ứng | **Memory** `preference` | "ngại commute", "muốn mentor tốt" |
| Cách user muốn agent trả lời | **Memory** `style` | format/style |

**Nguyên tắc**: lookup được bằng **SQL filter** → Profile. Chỉ dùng để **LLM personalize prompt** → Memory.

## Không làm

- Không quản lý `conversations` và `messages` — app backend làm
- Không quản lý free-form fact — Agent 2 Memory làm
- Không generate response trả user
- Không validate giá trị (vd salary có hợp lý không) — đó là logic của agent nghiệp vụ
- Không cross-call agent khác
- Không dùng Tavily

## Quyết định đã chốt

| Vấn đề | Quyết định |
|---|---|
| Storage | 1 bảng `user_profile`, JSON column cho arrays |
| History | Chỉ current (1 job, 1 highest degree) |
| Trigger | Song song với luồng chính, mỗi user input |
| Blacklist | `goal_*`, `mbti_type`, `holland_code`, `*_completed_at` — Profile KHÔNG ghi, kể cả user nói rõ |
| Strict extraction | Chỉ ghi khi user declarative về bản thân; bỏ qua bình luận / câu hỏi / hypothetical / mơ hồ |
| Salary unit | VND/tháng (BIGINT) |
| Languages format | Array of `{lang, level}` |
| Job preferences storage | Đặt ở Profile (work_mode, company_size_pref, preferred_industries) |
| Assessment results storage | Đặt ở Profile (mbti_type, holland_code) |
| Slot bắt buộc | Tất cả nullable, fill dần qua hội thoại |
| Khi LLM không nhắc 1 slot | Giữ nguyên (KHÔNG reset NULL) |
| Identity slot (name, age, gender, contact) | KHÔNG ở Profile — assume đã ở bảng `users` |
| Web search | Không dùng Tavily |
