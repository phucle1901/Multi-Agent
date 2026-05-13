# Agent 1 · Supervisor

## Mục đích

**CHỈ active khi user free chat** (không click group nào trên UI).

Nhiệm vụ: classify intent của message → route đến 1 trong 6 Group Manager. Nếu off-topic project → ask back.

Khi user click group card trên UI → Supervisor **bị skip hoàn toàn**, message vào thẳng Manager của group đó.

## Input / Output

| | |
|---|---|
| **Input** | user message (từ free chat input) + recent messages context |
| **Output** | route đến Manager X (A/B/C/D/E/F) **HOẶC** ask-back response gửi lại user |

## Cách hoạt động

LLM function calling với 6 function (1 per Manager):

```
manager_A: Khám phá bản thân (Goal Setting, MBTI/Holland)
manager_B: Tư vấn nghề nghiệp (Career Advisor, Skill Gap, Learning Path)
manager_C: Tìm việc làm (Job Search, Company)
manager_D: Phân tích thị trường (Market Insight, Salary)
manager_E: Tối ưu hồ sơ (CV Parser, Resume Builder, Cover Letter)
manager_F: Phỏng vấn & Đàm phán (Question Gen, Mock Interview, Negotiation)
```

Plus 1 fallback function `ask_back_off_topic()` cho off-topic / không thuộc scope project.

### Quy tắc

- Message rõ ràng thuộc 1 nhóm → route luôn.
- Message mơ hồ giữa 2-3 nhóm → hỏi lại user dạng câu hỏi có lựa chọn:
   > "Bạn muốn (1) tìm việc cụ thể, (2) định hướng nghề, hay (3) test xem có hợp ngành nào không?"
- Message off-topic project (vd "thời tiết hôm nay đẹp", "1+1=?") → trả response chung + redirect:
   > "Mình hỗ trợ tư vấn việc làm Hà Nội. Bạn quan tâm: định hướng nghề, tìm việc, phân tích thị trường, tối ưu CV, hay luyện phỏng vấn?"
- **Compound question (message thuộc ≥2 group)** → pick best-fit 1 Manager + append note flag phần còn lại:
   > "Câu của bạn có phần về [Y]. Mình xử lý phần [X] trước. Phần [Y] bạn hỏi lại sau hoặc chuyển sang nhóm Y nhé."
  
  Chi tiết → [0.0-modes-and-communication.md](./0.0-modes-and-communication.md). KHÔNG đa-Manager song song trong 1 turn.

Chi tiết logic phân loại / threshold → handle qua prompt engineering ở pha implement, không hard-code state machine.

## State sử dụng

### Đọc context

User message only + breadcrumb `handled_by` của các turn trước:

```sql
SELECT role, content, metadata->>'handled_by' AS handled_by
FROM messages
WHERE conversation_id = ?
  AND role = 'user'
ORDER BY created_at ASC
LIMIT N
```

Render dạng:
```
User turn 1: "Tìm việc DA HN"          [handled_by: manager_c]
User turn 2: "Lương DA bao nhiêu?"     [handled_by: manager_d]
User turn 3: "Lọc thêm 20-30tr"        ← đang classify
```

→ Supervisor thấy lịch sử routing → classify message hiện tại chính xác cả khi refine xuyên Manager.

KHÔNG load assistant content (nặng + thường không cần cho classify).

### Ghi

1. **Tag `handled_by` cho user msg N** sau khi classify:
   - Route Manager X → `UPDATE messages SET metadata = jsonb_set(metadata, '{handled_by}', '"manager_x"') WHERE id = N`
   - Ask-back → `UPDATE ... '"supervisor"'`
2. **INSERT assistant message** với `handled_by = 'supervisor'` **chỉ khi ask-back**. Nếu route Manager X clean → Supervisor không sinh assistant, Manager X tự sinh.
3. Memory subsystem ghi `memory_facts` song song (không phải việc của Supervisor).

Chi tiết flow & rule → [`0.0-modes-and-communication.md`](./0.0-modes-and-communication.md).

## Không làm

- Không entity extract (Profile làm)
- Không synthesize output từ nhiều nguồn (Group Manager làm)
- Không xử lý business logic
- Không active khi user click group qua UI

## TODO khi implement

- Build test set ~30-50 message ambiguous từ thực tế (câu cụt, multi-intent, slang Vietnamese, off-topic) để tune prompt + đo accuracy.
