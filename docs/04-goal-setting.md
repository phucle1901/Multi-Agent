# Agent 4 · Goal Setting

## Mục đích

**Coach giúp user DISCOVER goal nghề nghiệp** qua đối thoại phản tư.

KHÔNG phải interface form-fill — đây là agent đối thoại giúp user nghĩ ra mình muốn gì, rồi cô đọng thành 1 goal cụ thể.

## Vị trí trong kiến trúc

Goal Setting là sub-agent của **Manager A · Khám phá bản thân**. Được gọi bởi Manager A (không trực tiếp từ Supervisor / UI).

## Input / Output

| | |
|---|---|
| **Input** | User message + context (profile, assessment result nếu có) — chuyển từ Manager A |
| **Output** | Cập nhật goal cho user + response đối thoại cho Manager A tổng hợp |

## Hành vi

- **Multi-turn dialog**: hỏi câu phản tư về interest / strength / value → suggest direction → concretize → save
- **Đọc kết quả Assessment** nếu user đã làm trước đó → cá nhân hoá câu hỏi (vd "bạn ra Holland RIA, có vẻ hợp việc phân tích, bạn thấy đúng không?")
- **Đọc profile user** (current_role, education...) làm context discovery
- **Nếu user nói "không biết"** → gợi ý "thử Assessment trước nhé" → end session, user tự navigate sang Assessment (KHÔNG cross-call agent khác)
- **Khi save xong** → gợi ý next step (Skill Gap, Learning Path) trong response. KHÔNG tự chain.

## Required fields để goal "hợp lệ"

Goal được coi là đã set khi đủ 4 trường:
- `goal_type` — career_change / promotion / first_job / skill_acquisition
- `target_role` — vd "Data Analyst"
- `target_salary` (min/max) — range mong muốn
- `target_date` — deadline đạt được

Trước khi đủ 4 trường, Goal Setting tiếp tục hỏi.

## Đọc / Ghi dữ liệu

| | Bảng / Field |
|---|---|
| **Đọc** | user_profile (context discovery), assessment results (nếu có) |
| **Ghi** | 4 goal field tích hợp trong user_profile |

Goal được tích hợp **vào trong** user_profile, không tạo entity `user_goals` riêng.

## Không làm

- Không recommend nghề cụ thể (Career Advisor làm)
- Không chạy MBTI/Holland (Assessment làm)
- Không suggest course (Learning Path làm)
- Không cross-call agent khác

## Quyết định đã chốt

| Vấn đề | Quyết định |
|---|---|
| Mục đích | Coach discovery, không phải form-fill |
| Storage | Tích hợp vào user_profile, không có entity `user_goals` riêng |
| Multi-goal | Single active goal per user |
| Đổi goal | Overwrite, không archive history |
| Đọc Assessment | Có nếu có sẵn, để cá nhân hoá câu hỏi |
| Khi user unsure | Gợi ý Assessment, end session, user tự navigate |
| Required fields | 4 trường: goal_type, target_role, target_salary, target_date |
