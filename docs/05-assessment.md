# Agent 5 · Assessment

## Mục đích

Cho user làm test **MBTI** và **Holland (RIASEC)** theo chuẩn quốc tế, lưu kết quả vào `user_profile`, trả về mã code + interpretation mapping sẵn cho Manager A.

## Vị trí trong kiến trúc

Sub-agent của **Manager A · Khám phá bản thân**. Được gọi bởi Manager A, không trực tiếp từ Supervisor / UI.

## Input / Output

| | |
|---|---|
| **Input** | • Trigger từ Manager A kèm `test_type` ('mbti' / 'holland')<br>• Answers từ form khi user submit |
| **Output** | • Render inline form (1 lần, không multi-turn)<br>• Khi submit: scoring → ghi `user_profile` → trả `{code, interpretation}` cho Manager A tổng hợp |

## Flow

```
1. User: "muốn làm MBTI"
2. Manager A → call Assessment(test_type='mbti')
3. Agent load câu hỏi từ file JSON → render inline form trong chat
4. User chọn đáp án từng câu → submit 1 lần
5. Agent chạy scoring code deterministic (chuẩn quốc tế)
6. Agent lookup interpretation từ file mapping
7. Agent UPDATE user_profile SET mbti_type=..., mbti_completed_at=now()
8. Agent return {code: "INTJ", interpretation: {...}} cho Manager A
```

2 test **độc lập** — user có thể chỉ làm 1 trong 2, hoặc làm cả 2 ở các session khác nhau.

## Scoring — code deterministic (chuẩn quốc tế)

| Test | Cách tính |
|---|---|
| **MBTI** | 4 trục E/I, S/N, T/F, J/P. Mỗi câu hỏi gán cho 1 trục với hướng (+/-). Đếm point → majority mỗi trục → 4 chữ cái (vd "INTJ"). |
| **Holland (RIASEC)** | 6 nhóm R/I/A/S/E/C. Mỗi câu gán cho 1 nhóm. Tổng điểm → sort → top-3 letters (vd "RIA"). |

**KHÔNG dùng LLM cho scoring** — pure rule-based, kiểm soát được.

## Static files (không vào DB)

Theo nguyên tắc overview: static content → file JSON, không vào DB.

```
data/assessments/
  mbti_questions.json          # ~60 câu hỏi MBTI
  holland_questions.json       # ~60 câu hỏi Holland
  mbti_interpretations.json    # 16 type → schema cố định
  holland_interpretations.json # 6 letter → schema cố định
```

### Cấu trúc câu hỏi

**MBTI question**:
```json
{
  "id": "mbti_q01",
  "text": "Bạn thích...",
  "axis": "EI",                 // hoặc SN / TF / JP
  "direction": "E"               // câu này nghiêng về cực nào
}
```

**Holland question**:
```json
{
  "id": "holland_q01",
  "text": "Bạn thích...",
  "group": "R"                   // R/I/A/S/E/C
}
```

### Cấu trúc interpretation (cố định trước schema)

**MBTI** (16 entries, key = type code 4 chữ):
```json
"INTJ": {
  "name": "Architect",
  "tendencies": "Tư duy chiến lược, độc lập, thiên về phân tích dài hạn...",
  "suggested_industries": ["data", "strategy", "R&D", "engineering"],
  "suggested_roles": ["Data Scientist", "Strategy Consultant", "Architect"],
  "strengths": ["...", "..."],
  "growth_areas": ["...", "..."]
}
```

**Holland** (6 entries, key = single letter):
```json
"R": {
  "name": "Realistic",
  "desc": "Thực tế, thiên về làm việc với máy móc / công cụ / vật chất...",
  "industries": ["engineering", "manufacturing", "construction"],
  "roles": ["Mechanical Engineer", "Technician"]
},
"I": { ... }, "A": { ... }, "S": { ... }, "E": { ... }, "C": { ... }
```

Khi user ra top-3 (vd "RIA") → agent assemble từ 3 entry R + I + A.

## Storage trong user_profile

(Cập nhật so với schema gốc — tách timestamp cho 2 test)

| Field | Type | Note |
|---|---|---|
| `mbti_type` | CHAR(4) | "INTJ" |
| `holland_code` | CHAR(3) | "RIA" |
| `mbti_completed_at` | TIMESTAMPTZ | khi user xong MBTI |
| `holland_completed_at` | TIMESTAMPTZ | khi user xong Holland |

Không tạo bảng riêng. Không lưu chi tiết answer của từng câu.

## Retake → Overwrite

Làm test lại → UPDATE row hiện có. Không lưu lịch sử trước.

## Read API (cho agent khác)

Agent khác (Goal Setting, Career Advisor) đọc kết quả qua `get_profile(user_id)` — không gọi Agent 5 trực tiếp.

## Không làm

- Không recommend nghề cụ thể (Career Advisor làm)
- Không multi-turn chat hỏi từng câu (form 1-lần)
- Không sinh interpretation bằng LLM (lookup từ file mapping)
- Không lưu chi tiết answer (chỉ kết quả cuối)
- Không cross-call agent khác
- Không dùng Tavily

## Quyết định đã chốt

| Vấn đề | Quyết định |
|---|---|
| Loại test | MBTI + Holland, độc lập |
| UX | Form-style inline, submit 1 lần |
| Static content | File JSON (questions + interpretations) |
| Scoring | Code deterministic theo chuẩn quốc tế, không LLM |
| Output | Mã code + lookup interpretation từ file mapping (cố định) |
| Storage | Chỉ kết quả cuối vào `user_profile` |
| Detail answer | KHÔNG lưu |
| Retake | Overwrite, không lưu history |
| Timestamp | Tách `mbti_completed_at` + `holland_completed_at` |
| Web search | Không dùng Tavily |
