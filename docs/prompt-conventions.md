# Prompt conventions — nguyên lý thiết kế

File này ghi **nguyên lý** viết prompt cho mọi agent / function calling trong project. Để khi code, biết schema gì phải khai báo rõ → agent / function khác gọi đúng.

KHÔNG phải implementation guide. Chi tiết prompt cụ thể của từng agent → xem doc agent đó.

## Nguyên lý cốt lõi

> **Mọi LLM call có structured output PHẢI có schema rõ ràng trong prompt. KHÔNG để LLM tự đoán format.**

Nếu không tuân nguyên lý này: output không parse được, value sai ENUM, dispatch sai sub-agent, slot-fill DB sai → chuỗi sau gãy.

## 4 quy tắc

### 1. ENUM field — liệt kê values + description (BẮT BUỘC)

Field có giá trị hợp lệ cố định (ENUM DB column, ENUM logic) → prompt **luôn liệt kê** đầy đủ values + 1 câu mô tả mỗi value.

```
"work_mode": <enum>
  - "remote": làm từ xa hoàn toàn (WFH, work from home, tại nhà)
  - "hybrid": mix văn phòng + remote
  - "onsite": full văn phòng
  NULL nếu user không nhắc.
```

KHÔNG để LLM tự đoán string format.

### 2. Free-text với canonical list — cung cấp list normalization + typo tolerance

Field free-text nhưng cần normalize (skill name, role title, ngành, tên công ty) → prompt cung cấp **list canonical** + rule mapping. Đồng thời **dặn LLM tolerant với typo / viết tắt / variant** của user.

```
Skill name canonical: Python, PostgreSQL, MySQL, SQL Server, Tableau, ...

Mapping rules:
  - Variant: "Python 3.8" → "Python". "MS Excel" / "Excel nâng cao" → "Microsoft Excel".
  - Typo: "Pythn" → "Python". "Postgrest" → "PostgreSQL". (best-effort match
    với canonical list — pick closest)
  - Viết tắt: "JS" → "JavaScript". "TS" → "TypeScript".
  - Không khớp gì → giữ nguyên user nói (case-sensitive).
```

→ User gõ sai chính tả / dùng viết tắt → LLM vẫn map về canonical đúng.

### 3. Function calling — mỗi function có description + parameters schema rõ

Supervisor / Manager dispatch dùng function calling → mỗi function:
- **Name** rõ purpose (call_skill_gap, ask_back_off_group...)
- **Description** 1-2 câu nói khi nào dùng
- **Parameters** schema rõ (kèm ENUM nếu có)

LLM dispatch chính xác phụ thuộc 3 thứ này.

### 4. Null khi không có, KHÔNG bịa

Field nullable luôn explicit trong prompt:
```
NULL nếu user không nhắc / không tìm thấy / chưa rõ.
```

LLM bịa value > LLM trả null. Trả null vẫn dùng được (caveat), bịa value làm chuỗi sau sai.

## Áp dụng — xem doc từng agent

Mỗi agent doc có section "Input/Output schema" và "Prompt logic" — chi tiết ENUM, canonical list, function description áp dụng cho agent đó. File này chỉ là nguyên lý chung.

## Anti-patterns — KHÔNG làm

- ❌ Prompt "extract field X" không liệt kê ENUM
- ❌ Canonical list không có rule cho typo / variant / viết tắt → LLM strict-match, miss user input không chuẩn
- ❌ Function description mơ hồ ("xử lý câu hỏi") → LLM dispatch sai
- ❌ Schema không note nullable → LLM bịa
- ❌ Pass full DB schema khi không cần → noise

## Living document

Khi thêm pattern / quy tắc mới phát hiện trong implement → cập nhật file này.
