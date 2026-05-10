"""Parse các field text → kiểu dữ liệu queryable."""

import re
from datetime import datetime

USD_TO_TRIEU = 0.263

EXP_MAP = {
    "không yêu cầu": 0.0,
    "dưới 1 năm":    0.0,
    "1 năm":         1.0,
    "2 năm":         2.0,
    "3 năm":         3.0,
    "4 năm":         4.0,
    "5 năm":         5.0,
    "trên 5 năm":    5.0,
}
# Range: "10 - 15 triệu", "1,000 - 2,000 USD"
_RE_RANGE = re.compile(
    r"^\s*([\d.,]+)\s*-\s*([\d.,]+)\s*(triệu|USD)",
    re.IGNORECASE,
)
# Min only: "Từ 15 triệu", "Trên 10 triệu"
_RE_MIN   = re.compile(
    r"^\s*(?:Từ|Trên)\s+([\d.,]+)\s*(triệu|USD)",
    re.IGNORECASE,
)
# Max only: "Tới 20 triệu", "Đến 30 triệu", "Dưới 5 triệu"
_RE_MAX   = re.compile(
    r"^\s*(?:Tới|Đến|Dưới)\s+([\d.,]+)\s*(triệu|USD)",
    re.IGNORECASE,
)

def _to_float(s: str) -> float:
    return float(s.replace(",", ""))


def _convert(value: float, unit: str) -> float:
    """Đưa về triệu VNĐ. unit là 'triệu' hoặc 'USD'."""
    return value * USD_TO_TRIEU if unit.upper() == "USD" else value


def parse_salary(s):
    """
    Trả (min, max) đơn vị triệu VNĐ.

    - "10 - 15 triệu"        → (10,   15)
    - "1,000 - 2,000 USD"    → (263,  526)
    - "Từ 15 triệu"          → (15,   None)
    - "Trên 10 triệu"        → (10,   None)
    - "Tới 20 triệu"         → (None, 20)
    - "Đến 30 triệu"         → (None, 30)
    - "Dưới 5 triệu"         → (None, 5)
    - "Thoả thuận" / không match → (None, None)
    """
    if not s:
        return (None, None)
    s = s.strip()
    if s.lower() in ("thoả thuận", "thỏa thuận"):
        return (None, None)

    m = _RE_RANGE.match(s)
    if m:
        return (_convert(_to_float(m.group(1)), m.group(3)),
                _convert(_to_float(m.group(2)), m.group(3)))

    m = _RE_MIN.match(s)
    if m:
        return (_convert(_to_float(m.group(1)), m.group(2)), None)

    m = _RE_MAX.match(s)
    if m:
        return (None, _convert(_to_float(m.group(1)), m.group(2)))

    return (None, None)

def parse_experience(s):
    """'5 năm' → 5.0, 'Không yêu cầu' → 0.0, khác → None."""
    if not s:
        return None
    return EXP_MAP.get(s.strip().lower())


def parse_deadline(s):
    """'04/04/2026' → '2026-04-04'. None nếu lỗi format."""
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%d/%m/%Y").date().isoformat()
    except (ValueError, TypeError):
        return None
