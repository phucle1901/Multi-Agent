"""Xây dựng text embedding từ job dict.

Pure functions, dễ test và tái sử dụng.
"""

import logging

import tiktoken

logger = logging.getLogger(__name__)

# OpenAI text-embedding-3-small giới hạn 8191 tokens/input.
# Cap về 8000 chừa buffer cho special tokens.
_MAX_EMBEDDING_TOKENS = 8000

_encoding = None


def _get_encoding():
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding("cl100k_base")
    return _encoding


def build_embedding_text(job: dict) -> str | None:
    """Tạo text để embed từ 1 job dict.

    Returns None nếu job không có đủ thông tin (lỗi crawl).
    Tự động truncate khi text vượt _MAX_EMBEDDING_TOKENS để tránh OpenAI 400.
    """
    if not job.get("title") and not job.get("job_description"):
        return None

    parts = []

    # Header fields — mỗi field 1 dòng có label
    field_map = [
        ("Vị trí", "title"),
        ("Công ty", "company_name"),
        ("Lĩnh vực", "company_field"),
        ("Mức lương", "salary"),
        ("Kinh nghiệm", "experience"),
        ("Cấp bậc", "level"),
        ("Hình thức", "work_type"),
        ("Khu vực", "location"),
    ]
    for label, key in field_map:
        value = job.get(key)
        if value:
            parts.append(f"{label}: {value}")

    # loai_job là list → join thành chuỗi
    loai_job = job.get("loai_job")
    if loai_job:
        parts.append(f"Ngành nghề: {', '.join(loai_job)}")

    # Long-form fields — có heading riêng
    long_fields = [
        ("Mô tả công việc", "job_description"),
        ("Yêu cầu ứng viên", "requirements"),
        ("Quyền lợi", "benefits"),
    ]
    for label, key in long_fields:
        value = job.get(key)
        if value:
            parts.append(f"\n{label}:\n{value}")

    text = "\n".join(parts)

    enc = _get_encoding()
    tokens = enc.encode(text)
    if len(tokens) > _MAX_EMBEDDING_TOKENS:
        truncated_tokens = tokens[:_MAX_EMBEDDING_TOKENS]
        text = enc.decode(truncated_tokens)
        logger.warning(
            "Truncated embedding text from %d to %d tokens for link_job=%s",
            len(tokens),
            _MAX_EMBEDDING_TOKENS,
            job.get("link_job", "<unknown>"),
        )

    return text
