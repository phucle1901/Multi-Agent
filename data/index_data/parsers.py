"""Parser pure functions: salary/experience/deadline + normalize phuong/company/size."""
from __future__ import annotations

import re
from datetime import datetime

from data.index_data.config import USD_TO_VND


def parse_salary(raw: str | None) -> tuple[int | None, int | None]:
    """'X - Y triệu' → (X*1e6, Y*1e6). USD → ×USD_TO_VND. 'Thoả thuận'/None → (None, None)."""
    if not raw:
        return None, None
    s = raw.strip().lower()
    if 'thoả thuận' in s or 'thỏa thuận' in s or 'negotiable' in s:
        return None, None
    is_usd = 'usd' in s or '$' in s
    mult = USD_TO_VND if is_usd else 1_000_000

    m = re.search(r'(\d+(?:[.,]\d+)?)\s*-\s*(\d+(?:[.,]\d+)?)', s)
    if m:
        a = float(m.group(1).replace(',', '.'))
        b = float(m.group(2).replace(',', '.'))
        return round(a * mult), round(b * mult)

    m = re.search(r'từ\s*(\d+(?:[.,]\d+)?)', s)
    if m:
        return round(float(m.group(1).replace(',', '.')) * mult), None

    m = re.search(r'(?:tới|đến)\s*(\d+(?:[.,]\d+)?)', s)
    if m:
        return None, round(float(m.group(1).replace(',', '.')) * mult)

    m = re.search(r'(\d+(?:[.,]\d+)?)', s)
    if m:
        v = round(float(m.group(1).replace(',', '.')) * mult)
        return v, v

    return None, None


def parse_experience(raw: str | None) -> float | None:
    """'Dưới 1 năm'/'Không yêu cầu' → 0.0. 'N năm' → N. 'Trên 5 năm' → 5.0. Khác → None."""
    if not raw:
        return None
    s = raw.strip().lower()
    if 'không yêu cầu' in s or 'dưới 1' in s:
        return 0.0
    if 'trên 5' in s:
        return 5.0
    m = re.search(r'(\d+(?:\.\d+)?)\s*năm', s)
    if m:
        return float(m.group(1))
    return None


def parse_deadline(raw: str | None) -> str | None:
    """'DD/MM/YYYY' → 'YYYY-MM-DD'. Invalid → None."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), '%d/%m/%Y').strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return None


def normalize_phuong(raw: str) -> str:
    """'  phường lĩnh nam  ' → 'phường Lĩnh Nam'. Prefix lowercase, rest title-case."""
    s = re.sub(r'\s+', ' ', raw.strip())
    for prefix in ('phường', 'xã'):
        if s.lower().startswith(prefix + ' '):
            return f"{prefix} {s[len(prefix)+1:].title()}"
    return s.title()


def normalize_company(raw: str) -> str:
    """Trim + collapse whitespace. Giữ case."""
    return re.sub(r'\s+', ' ', raw.strip())


def derive_size_bucket(size_raw: str | None) -> str | None:
    """Parse số nhỏ nhất từ '25-99 nhân viên'. <25→startup, 25-499→sme, ≥500→large_corp."""
    if not size_raw:
        return None
    m = re.search(r'(\d+)', size_raw)
    if not m:
        return None
    n = int(m.group(1))
    if n < 25:
        return 'startup'
    if n < 500:
        return 'sme'
    return 'large_corp'


if __name__ == "__main__":
    # Salary
    assert parse_salary("60 - 100 triệu") == (60_000_000, 100_000_000)
    assert parse_salary("Từ 10 triệu") == (10_000_000, None)
    assert parse_salary("Tới 20 triệu") == (None, 20_000_000)
    assert parse_salary("Đến 20 triệu") == (None, 20_000_000)
    assert parse_salary("15 triệu") == (15_000_000, 15_000_000)
    assert parse_salary("1000 - 1500 USD") == (26_000_000, 39_000_000)
    assert parse_salary("Thoả thuận") == (None, None)
    assert parse_salary("Thỏa thuận") == (None, None)
    assert parse_salary("Negotiable") == (None, None)
    assert parse_salary(None) == (None, None)
    assert parse_salary("") == (None, None)

    # Experience
    assert parse_experience("Dưới 1 năm") == 0.0
    assert parse_experience("Không yêu cầu") == 0.0
    assert parse_experience("1 năm") == 1.0
    assert parse_experience("5 năm") == 5.0
    assert parse_experience("Trên 5 năm") == 5.0
    assert parse_experience(None) is None
    assert parse_experience("abc") is None

    # Deadline
    assert parse_deadline("12/04/2026") == "2026-04-12"
    assert parse_deadline("31/12/2025") == "2025-12-31"
    assert parse_deadline("abc") is None
    assert parse_deadline(None) is None

    # Phuong
    assert normalize_phuong("phường lĩnh nam") == "phường Lĩnh Nam"
    assert normalize_phuong("  phường  Ba Đình  ") == "phường Ba Đình"
    assert normalize_phuong("xã bát tràng") == "xã Bát Tràng"
    assert normalize_phuong("phường Ba Đình") == "phường Ba Đình"

    # Company
    assert normalize_company("  FPT  Software ") == "FPT Software"

    # Size bucket
    assert derive_size_bucket("10-25 nhân viên") == "startup"
    assert derive_size_bucket("25-99 nhân viên") == "sme"
    assert derive_size_bucket("100-499 nhân viên") == "sme"
    assert derive_size_bucket("500-1000 nhân viên") == "large_corp"
    assert derive_size_bucket("1000+ nhân viên") == "large_corp"
    assert derive_size_bucket(None) is None
    assert derive_size_bucket("ít người") is None

    print("Tất cả test PASS")
