# Kiến trúc tổng quan — 24 agent

## Phân tầng

```
┌─────────────────────────────────────────────────────────────────┐
│  UI                                                              │
│   • 6 group card — user click để vào group cụ thể                │
│   • Free chat input — user gõ tự do                              │
└─────────────────────────────────────────────────────────────────┘
     ↓ click group X                ↓ free chat
                                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  Hạ tầng (3 agent) — chạy song song mỗi turn                    │
│   1 · Supervisor — CHỈ active khi free chat (không click)        │
│                    classify → route đến group HOẶC ask back      │
│                    nếu off-topic project                         │
│   2 · Memory     — quản lý messages + curate facts (subsystem)  │
│   3 · Profile    — slot-fill user_profile (subsystem)           │
└─────────────────────────────────────────────────────────────────┘
     ↓ UI direct                    ↓ Supervisor route
                  ↓
┌─────────────────────────────────────────────────────────────────┐
│  Tầng điều phối · 6 Group Manager (1 cho mỗi nhóm)              │
│   Manager A — Khám phá bản thân                                  │
│   Manager B — Tư vấn nghề nghiệp                                 │
│   Manager C — Tìm việc làm                                       │
│   Manager D — Phân tích thị trường                               │
│   Manager E — Tối ưu hồ sơ                                       │
│   Manager F — Phỏng vấn & đàm phán                               │
│                                                                  │
│   Trách nhiệm:                                                   │
│    • Chain sub-agent trong nhóm khi cần nhiều bước               │
│    • Ask back user nếu câu hỏi ngoài scope nhóm                  │
│    • Tổng hợp output từ sub-agent thành 1 response markdown      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Tầng nghiệp vụ · 15 agent chuyên biệt                          │
│   A: 4 Goal Setting · 5 Assessment                               │
│   B: 6 Career Advisor · 7 Skill Gap · 8 Learning Path            │
│   C: 9 Job Search · 10 Company                                   │
│   D: 11 Market Insight · 12 Salary                               │
│   E: 13 CV Parser · 14 Resume Builder · 15 Cover Letter          │
│   F: 16 Question Gen · 17 Mock Interview · 18 Negotiation        │
└─────────────────────────────────────────────────────────────────┘
```

**Tổng**: 3 hạ tầng + 6 Group Manager + 15 nghiệp vụ = **24 agent**.

## 2 entry path

| Path | Khi nào | Flow |
|---|---|---|
| **UI click** | User chọn 1 trong 6 card từ UI | Skip Supervisor → vào thẳng Manager của group đó |
| **Free chat** | User gõ tự do (không click) | Supervisor classify → route đến Manager phù hợp / ask back nếu off-topic |

Cả 2 path đều converge ở **Group Manager** — đây là entry point thật sự của tầng nghiệp vụ.

## Nguyên tắc chung

- **Ưu tiên đơn giản** trong mọi quyết định thiết kế.
- **Không tạo bảng cache**. Tính được live thì tính live.
- **Không persist output** của agent stateless (Mock Interview, Learning Path, Negotiation...).
- **Static content → file JSON/MD** (MBTI/Holland questions, resume templates), không vào DB.
- **Qdrant scope hạn chế**: chủ yếu cho `jobs`. Collection khác cần justify rõ.
- **Multi-user từ đầu**: mọi bảng user-scoped FK → `users.id`.
- **Edge case ở prompt**: phần lớn xử lý ambiguous / mơ hồ / off-scope thông qua prompt engineering của Supervisor + Group Manager, không build state machine phức tạp.
