"""Đường dẫn tập trung cho importer."""

from pathlib import Path

# .../build_code_new
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR  = PROJECT_ROOT / "data"
JSON_PATH = DATA_DIR / "job_details.json"
DB_PATH   = DATA_DIR / "jobs.db"
