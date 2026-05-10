"""Cấu hình tập trung cho module embedding, overridable qua biến môi trường.

Airflow hoặc pipeline chỉ cần set env vars để thay đổi config,
không cần sửa code.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env từ project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# --- OpenAI ---
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-3-small")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "200"))

# --- Qdrant ---
QDRANT_URL = os.environ["QDRANT_URL"]
QDRANT_API_KEY = os.environ["QDRANT_API_KEY"]
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "jobs")
QDRANT_UPSERT_BATCH = int(os.getenv("QDRANT_UPSERT_BATCH", "100"))

# --- Input data ---
EMBEDDING_INPUT_FILE = os.getenv(
    "EMBEDDING_INPUT_FILE",
    str(PROJECT_ROOT / "data" / "job_details.json"),
)
