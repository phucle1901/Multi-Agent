"""Entry points cho embedding pipeline.

Mỗi function tương ứng 1 task trong Airflow DAG.
Cũng chạy được qua CLI: python -m embedding.tasks <task_name>

Sử dụng:
    - Airflow PythonOperator: gọi trực tiếp function
    - CLI: python -m embedding.tasks embed [--force]
    - CLI: python -m embedding.tasks delete_expired [--before DD/MM/YYYY]
    - Pipeline: from embedding.tasks import embed_jobs
"""

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

from tqdm import tqdm
from qdrant_client.models import PointStruct

from embedding import config
from embedding.text_builder import build_embedding_text
from embedding.embedding_model import EmbeddingModel
from embedding.qdrant_manager import QdrantManager, job_to_point_id

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def embed_jobs(jobs: list[dict], force: bool = False) -> int:
    """Core function — embed list of job dicts vào Qdrant.

    Nhận input là list dicts từ bất kỳ nguồn nào (file, Spark, Kafka).
    Returns số jobs đã embed thành công.
    """
    if not jobs:
        logger.info("No jobs to embed")
        return 0

    model = EmbeddingModel()
    qdrant = QdrantManager()
    qdrant.ensure_collection(vector_size=model.dimension)

    # Resume: skip jobs đã có trong Qdrant
    if not force:
        existing_links = qdrant.get_existing_links()
        before_count = len(jobs)
        jobs = [j for j in jobs if j.get("link_job") not in existing_links]
        skipped = before_count - len(jobs)
        if skipped:
            logger.info("Skipped %d jobs already in Qdrant", skipped)

    if not jobs:
        logger.info("All jobs already embedded, nothing to do")
        return 0

    # Build text cho từng job
    valid_jobs = []
    valid_texts = []
    for job in jobs:
        text = build_embedding_text(job)
        if text is None:
            continue
        valid_jobs.append(job)
        valid_texts.append(text)

    invalid_count = len(jobs) - len(valid_jobs)
    if invalid_count:
        logger.warning("Skipped %d invalid jobs (missing title + description)", invalid_count)

    logger.info("Embedding %d jobs...", len(valid_texts))

    # Batch embedding + upsert
    embedded_count = 0
    embed_batch_size = config.EMBEDDING_BATCH_SIZE
    upsert_batch_size = config.QDRANT_UPSERT_BATCH

    # Tạo progress bar
    pbar = tqdm(total=len(valid_texts), desc="Embedding & uploading", unit="jobs")

    points_buffer = []
    failed_links: list[str] = []

    for i in range(0, len(valid_texts), embed_batch_size):
        batch_texts = valid_texts[i : i + embed_batch_size]
        batch_jobs = valid_jobs[i : i + embed_batch_size]

        success_pairs, batch_failed = _embed_batch_with_fallback(model, batch_texts, batch_jobs)
        failed_links.extend(batch_failed)
        # Skipped failed items must vẫn advance progress bar
        if batch_failed:
            pbar.update(len(batch_failed))

        # Tạo PointStruct cho mỗi job thành công
        for job, vector in success_pairs:
            point_id = job_to_point_id(job["link_job"])
            points_buffer.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=job,
                )
            )

            # Upsert khi buffer đủ lớn
            if len(points_buffer) >= upsert_batch_size:
                qdrant.upsert_batch(points_buffer)
                embedded_count += len(points_buffer)
                pbar.update(len(points_buffer))
                points_buffer = []

    # Upsert phần còn lại
    if points_buffer:
        qdrant.upsert_batch(points_buffer)
        embedded_count += len(points_buffer)
        pbar.update(len(points_buffer))

    pbar.close()

    if failed_links:
        failed_path = Path(config.PROJECT_ROOT) / "failed_embedding_links.txt" if hasattr(config, "PROJECT_ROOT") else Path("failed_embedding_links.txt")
        try:
            with open(failed_path, "w", encoding="utf-8") as f:
                for link in failed_links:
                    f.write(link + "\n")
            logger.warning(
                "%d jobs failed to embed (saved to %s)",
                len(failed_links),
                failed_path,
            )
        except Exception:
            logger.exception("Failed to write failed_embedding_links.txt; failures: %s", failed_links[:5])

    logger.info(
        "Done! Embedded %d jobs into Qdrant (%d failed)",
        embedded_count,
        len(failed_links),
    )
    return embedded_count


def _embed_batch_with_fallback(
    model: EmbeddingModel,
    texts: list[str],
    jobs: list[dict],
) -> tuple[list[tuple[dict, list[float]]], list[str]]:
    """Embed cả batch một lần. Nếu OpenAI reject → fallback embed từng item để
    không cho 1 record xấu làm hỏng cả batch.

    Returns:
        (success_pairs, failed_links) — success_pairs là list (job, vector).
    """
    try:
        vectors = model.embed(texts)
        return list(zip(jobs, vectors)), []
    except Exception as e:
        logger.warning(
            "Batch embed failed (size=%d): %s — falling back to per-item",
            len(texts),
            e,
        )

    success: list[tuple[dict, list[float]]] = []
    failed: list[str] = []
    for job, text in zip(jobs, texts):
        try:
            vec = model.embed([text])[0]
            success.append((job, vec))
        except Exception as ie:
            link = job.get("link_job", "<unknown>")
            logger.error("Failed to embed job %s: %s", link, ie)
            failed.append(link)
    return success, failed


def embed_from_file(input_file: str | None = None, force: bool = False) -> int:
    """Load jobs từ JSON file rồi embed.

    Tự deduplicate theo link_job .
    """
    input_file = input_file or config.EMBEDDING_INPUT_FILE
    logger.info("Loading jobs from %s", input_file)

    with open(input_file, encoding="utf-8") as f:
        jobs = json.load(f)

    logger.info("Loaded %d jobs", len(jobs))

    # Deduplicate: merge xa_phuong + loai_job, giữ bản ghi đầy đủ nhất cho các field còn lại
    seen = {}
    for job in jobs:
        link = job.get("link_job")
        if not link:
            continue
        if link not in seen:
            seen[link] = job
        else:
            existing = seen[link]
            # Merge xa_phuong và loai_job (union 2 list, bỏ trùng)
            for list_field in ("xa_phuong", "loai_job"):
                old_vals = set(existing.get(list_field) or [])
                new_vals = set(job.get(list_field) or [])
                merged = sorted(old_vals | new_vals)
                existing[list_field] = merged
            # Các field scalar: lấy giá trị non-None từ bản ghi mới nếu bản cũ thiếu
            for key, val in job.items():
                if key in ("link_job", "xa_phuong", "loai_job"):
                    continue
                if existing.get(key) is None and val is not None:
                    existing[key] = val

    unique_jobs = list(seen.values())
    deduped = len(jobs) - len(unique_jobs)
    if deduped:
        logger.info("Deduplicated: %d → %d unique jobs", len(jobs), len(unique_jobs))

    return embed_jobs(unique_jobs, force=force)


_DEADLINE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y")


def _parse_deadline(text: str) -> datetime | None:
    """Parse deadline string, thử nhiều format. Trả None nếu không parse được."""
    if not text:
        return None
    for fmt in _DEADLINE_FORMATS:
        try:
            return datetime.strptime(str(text).strip(), fmt)
        except ValueError:
            continue
    return None


def delete_expired_jobs(deadline_before: str | None = None) -> int:
    """Xóa jobs hết hạn khỏi Qdrant.

    Args:
        deadline_before: Ngày cutoff. Hỗ trợ DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY.
            Mặc định là hôm nay.
    """
    if deadline_before is None:
        cutoff = datetime.now()
    else:
        cutoff = _parse_deadline(deadline_before)
        if cutoff is None:
            raise ValueError(
                f"Định dạng ngày không hợp lệ: {deadline_before!r}. "
                f"Hỗ trợ: {', '.join(_DEADLINE_FORMATS)}"
            )

    logger.info("Deleting jobs with deadline before %s", cutoff.strftime("%d/%m/%Y"))

    qdrant = QdrantManager()

    expired_links = []
    unparseable = 0
    offset = None

    while True:
        results, offset = qdrant._client.scroll(
            collection_name=qdrant._collection,
            limit=1000,
            offset=offset,
            with_payload=["link_job", "deadline"],
            with_vectors=False,
        )
        for point in results:
            deadline_str = point.payload.get("deadline")
            link = point.payload.get("link_job")
            if not deadline_str or not link:
                continue
            deadline = _parse_deadline(deadline_str)
            if deadline is None:
                unparseable += 1
                continue
            if deadline < cutoff:
                expired_links.append(link)

        if offset is None:
            break

    if unparseable:
        logger.warning("Skipped %d jobs with unparseable deadline", unparseable)

    if not expired_links:
        logger.info("No expired jobs found")
        return 0

    logger.info("Found %d expired jobs, deleting...", len(expired_links))
    qdrant.delete_by_links(expired_links)
    return len(expired_links)


def main():
    parser = argparse.ArgumentParser(description="Embedding pipeline tasks")
    subparsers = parser.add_subparsers(dest="task", required=True)

    # embed
    embed_parser = subparsers.add_parser("embed", help="Embed jobs vào Qdrant")
    embed_parser.add_argument("--input", help="Path to job_details.json")
    embed_parser.add_argument(
        "--force", action="store_true", help="Re-embed tất cả (không skip existing)"
    )

    # delete_expired
    del_parser = subparsers.add_parser("delete_expired", help="Xóa jobs hết hạn")
    del_parser.add_argument(
        "--before", help="Cutoff date (DD/MM/YYYY), default: today"
    )

    args = parser.parse_args()

    if args.task == "embed":
        embed_from_file(input_file=args.input, force=args.force)
    elif args.task == "delete_expired":
        delete_expired_jobs(deadline_before=args.before)


if __name__ == "__main__":
    main()
