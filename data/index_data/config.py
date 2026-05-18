"""Config cho pipeline data layer."""
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
# Đường dẫn: parents[2] = Multi-Agent/
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
JOB_DETAILS_JSON = DATA_DIR / "job_details.json"
DB_PATH = DATA_DIR / "app.db"
SCHEMA_SQL = Path(__file__).resolve().parent / "schema.sql"

# Embedding
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "BAAI/bge-m3")
VECTOR_SIZE = int(os.getenv("VECTOR_SIZE", "1024"))
EMBED_BATCH = int(os.getenv("EMBED_BATCH", "32"))
MAX_SEQ_LEN = int(os.getenv("MAX_SEQ_LEN", "8192"))
EMBED_DEVICE = os.getenv("EMBED_DEVICE")  # None = auto-detect

# Qdrant
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_UPSERT_BATCH = int(os.getenv("QDRANT_UPSERT_BATCH", "200"))
COLLECTION_JOBS = os.getenv("COLLECTION_JOBS", "jobs")
COLLECTION_TITLES = os.getenv("COLLECTION_TITLES", "job_titles")

# Parser
USD_TO_VND = 26_000


def detect_device() -> str:
    if EMBED_DEVICE:
        return EMBED_DEVICE
    import torch
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


if __name__ == "__main__":
    print("PROJECT_ROOT:", PROJECT_ROOT)
    print("JOB_DETAILS: ", JOB_DETAILS_JSON, "OK" if JOB_DETAILS_JSON.exists() else "MISSING")
    print("DB_PATH:     ", DB_PATH)
    print("MODEL:       ", EMBED_MODEL_NAME, "/", VECTOR_SIZE, "D")
    print("DEVICE:      ", detect_device())
    print("QDRANT_URL:  ", "set" if QDRANT_URL else "MISSING")
    print("QDRANT_KEY:  ", "set" if QDRANT_API_KEY else "MISSING")
