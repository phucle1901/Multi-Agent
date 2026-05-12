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
3. LLM output: dict các slot cần update (chỉ những slot LLM tin có thay đổi)
   vd: {"target_role": "Data Analyst", "target_salary_max_vnd": 25000000}
4. UPDATE user_profile SET ... WHERE user_id = X
```

**Slot không nhắc → giữ nguyên.** KHÔNG reset về NULL khi LLM không thấy thông tin trong turn này.

## Schema — bảng `user_profile`

1 row : 1 user (1:1 với bảng `users`).

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
| `languages` | JSONB DEFAULT `'[]'` | `[{"lang":"English","level":"B2/IELTS 6.5"},{"lang":"Japanese","level":"N3"}]` |
| `certificates` | JSONB DEFAULT `'[]'` | `["AWS SAA","PMP"]` |
| **— Goal —** | | |
| `goal_type` | ENUM('career_change','promotion','first_job','skill_acquisition') | nullable |
| `target_role` | TEXT | "Data Analyst" |
| `target_salary_min_vnd` | BIGINT | VND/tháng |
| `target_salary_max_vnd` | BIGINT | VND/tháng |
| `target_date` | DATE | deadline đạt được goal |
| `target_location` | TEXT | "Cầu Giấy" / "Hà Nội" / "remote" |
| **— Assessment —** | | |
| `mbti_type` | CHAR(4) | "INTJ" |
| `holland_code` | CHAR(3) | "RIA" |
| `mbti_completed_at` | TIMESTAMPTZ | khi user xong MBTI |
| `holland_completed_at` | TIMESTAMPTZ | khi user xong Holland |
| **— Job preferences —** | | |
| `work_mode` | ENUM('remote','hybrid','onsite') | nullable |
| `company_size_pref` | ENUM('startup','sme','large_corp') | nullable |
| `preferred_industries` | JSONB DEFAULT `'[]'` | `["fintech","edtech"]` |
| **— Meta —** | | |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ DEFAULT now() | |

**Tất cả slot nullable** — Profile fill dần qua hội thoại, không bắt buộc đầy đủ.

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
| Hoàn cảnh hiện tại / event tạm | **Memory** `context` | có thời hạn ngắn |
| Cảm xúc / tâm lý | **Memory** `emotion` | ảnh hưởng tông response |
| Cách user muốn agent trả lời | **Memory** `interaction_meta` | format/style |

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
| Salary unit | VND/tháng (BIGINT) |
| Languages format | Array of `{lang, level}` |
| Job preferences storage | Đặt ở Profile (work_mode, company_size_pref, preferred_industries) |
| Assessment results storage | Đặt ở Profile (mbti_type, holland_code) |
| Slot bắt buộc | Tất cả nullable, fill dần qua hội thoại |
| Khi LLM không nhắc 1 slot | Giữ nguyên (KHÔNG reset NULL) |
| Identity slot (name, age, gender, contact) | KHÔNG ở Profile — assume đã ở bảng `users` |
| Web search | Không dùng Tavily |
