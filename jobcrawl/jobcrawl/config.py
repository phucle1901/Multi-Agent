"""Cấu hình đường dẫn tập trung, overridable qua biến môi trường.

Airflow hoặc pipeline chỉ cần set env vars để thay đổi paths,
không cần sửa code.
"""

import os
from pathlib import Path

# Thư mục gốc của project jobcrawl (chứa scrapy.cfg)
BASE_DIR = Path(
    os.getenv("JOBCRAWL_BASE_DIR", Path(__file__).resolve().parent.parent)
)

# Bước 1: Input URL đã lọc theo phường/xã + loại job
URL_INPUT = os.getenv(
    "JOBCRAWL_URL_INPUT",
    str(BASE_DIR / "url3.json"),
)

# Bước 2: Output danh sách link job (có trùng lặp)
LINKS_JOB_OUTPUT = os.getenv(
    "JOBCRAWL_LINKS_OUTPUT",
    str(BASE_DIR / "links_job.json"),
)

# Bước 3: Output sau khi gộp trùng
MERGED_LINKS = os.getenv(
    "JOBCRAWL_MERGED_LINKS",
    str(BASE_DIR / "merged_links.json"),
)

# Bước 4: Output chi tiết job
JOB_DETAILS = os.getenv(
    "JOBCRAWL_JOB_DETAILS",
    str(BASE_DIR / "job_details.json"),
)
