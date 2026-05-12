# Agent 2 · Memory

## Mục đích

Extract free-form fact **dài hạn** về user từ hội thoại, không khớp slot structured của Profile. Là "trí nhớ mềm" giúp các agent nghiệp vụ personalize response.

## Vị trí trong kiến trúc

Hạ tầng. Chạy **mỗi turn**, **song song** với luồng chính (không block Supervisor / Manager / sub-agent).

```
User gửi input ──┬─► Supervisor → Manager → sub-agent → response   (luồng chính)
                 ├─► Agent 2 · Memory     (song song)
                 └─► Agent 3 · Profile    (song song)
```

Hệ quả của parallel:
- Sub-agent trong **cùng turn** đọc facts ở turn N-1 (chưa thấy fact mới của turn N). Chấp nhận trade-off vì fact mới chưa kịp validate.
- Agent 2 KHÔNG đọc được assistant response đang sinh ra của turn hiện tại — nhưng đọc được assistant response của các turn TRƯỚC (đã save trong `messages`), đủ context.

## Input / Output

| | |
|---|---|
| **Input** | user message vừa nhận + N message gần nhất từ conversation (đã save) + facts hiện có của user (filter theo category) |
| **Output** | Các operation CRUD trên bảng `memory_facts` (insert / update / delete) |

## Write logic (mỗi turn)

```
1. Đọc facts hiện có của user (top N mới nhất, filter theo category)
2. LLM nhận: (existing facts) + (recent messages) + (user message mới)
3. LLM output operations:
   [
     {op: "insert", category, content},
     {op: "update", id, new_content},
     {op: "delete", id}   // hard delete
   ]
4. Execute trên DB
```

## 4 category của fact

| Category | Ý nghĩa | Ví dụ content |
|---|---|---|
| `preference` | Sở thích / xu hướng cá nhân **dài hạn** KHÔNG khớp slot Profile | "ngại commute xa", "không thích corporate culture", "muốn mentor tốt", "ưu tiên lương hơn WLB" |
| `context` | Hoàn cảnh / tình huống **hiện tại** đang chi phối user (có thời hạn) | "đang chuẩn bị phỏng vấn FPT ngày 25/5", "vừa nghỉ MoMo tháng trước", "đang học SQL tuần 3 Coursera" |
| `emotion` | Cảm xúc / trạng thái tâm lý — ảnh hưởng tông giọng của agent khi response | "lo lắng về deadline tốt nghiệp", "mất tự tin sau phỏng vấn fail", "hưng phấn với data eng" |
| `interaction_meta` | Cách user muốn agent giao tiếp (format / style) | "thích câu trả lời ngắn", "muốn hiển thị dạng bảng", "không thích bị hỏi nhiều câu cùng lúc" |

## Schema — bảng `memory_facts`

| Column | Type | Note |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `user_id` | BIGINT FK users.id NOT NULL | |
| `category` | ENUM('preference','context','emotion','interaction_meta') NOT NULL | agent filter theo cái này |
| `content` | TEXT NOT NULL | 1 câu tự nhiên, ngắn (≤ ~200 char) |
| `source_conversation_id` | BIGINT FK conversations.id NULL | debug / audit only |
| `source_message_id` | BIGINT FK messages.id NULL | debug / audit only |
| `created_at` | TIMESTAMPTZ DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ DEFAULT now() | dùng cho "recent" |

**Index chính**: `(user_id, category, updated_at DESC)` — phủ 95% query của agent khác.

## Read API cho agent khác

```python
get_facts(
    user_id: int,
    categories: list[str] | None = None,   # None = all 4
    limit: int = 30
) -> list[Fact]
```

Trả về list `Fact(id, category, content, updated_at)` — agent paste vào prompt theo nhu cầu.

### Helper format-cho-prompt

```python
get_facts_as_prompt_block(user_id, categories=None) -> str
# →
# ## Trí nhớ về user
# ### Sở thích
# - ngại commute xa
# - không thích corporate culture
# ### Hoàn cảnh hiện tại
# - đang chuẩn bị phỏng vấn FPT 25/5
```

## Write API (chỉ Agent 2 dùng nội bộ)

```python
upsert_facts(user_id, operations: list[Op])
# Op = {op: "insert"|"update"|"delete", category?, content?, id?}
```

## Ranh giới với Profile

| Loại thông tin | Đi đâu |
|---|---|
| Lookup được bằng SQL filter (current_role, target_role, MBTI, work_mode, skills...) | **Profile** |
| Chỉ dùng để LLM personalize prompt | **Memory** |

Cùng 1 turn có thể vừa update Profile vừa thêm Memory fact — 2 agent chạy độc lập song song.

## Không làm

- Không quản lý `conversations` và `messages` — app backend tự ghi khi user tạo / nhắn
- Không quản lý structured slot — Agent 3 Profile làm
- Không generate response trả user
- Không cross-call agent khác
- Không dùng Tavily — chỉ làm việc trên data nội bộ (messages của chính user)

## Quyết định đã chốt

| Vấn đề | Quyết định |
|---|---|
| Conversations + messages | App backend tự ghi, KHÔNG qua agent |
| Trigger | Song song với luồng chính, mỗi user input |
| Fact category | 4 enum: preference, context, emotion, interaction_meta |
| Update conflict | Overwrite — LLM tự decide insert/update/delete khi extract |
| Delete style | Hard delete (không soft-delete) |
| Traceability | Lưu `source_conversation_id` + `source_message_id` |
| Read pattern | Filter theo category + recent (`updated_at DESC`) |
| Embedding | Không (đơn giản hoá) |
| Web search | Không dùng Tavily |
