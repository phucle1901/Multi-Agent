"""Quản lý Qdrant collection: tạo, upsert, delete, search."""

import uuid
import logging

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
    PayloadSchemaType,
)

from embedding import config

logger = logging.getLogger(__name__)

# Namespace cố định cho uuid5 — đảm bảo deterministic ID
_UUID_NAMESPACE = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")  # NAMESPACE_URL


def job_to_point_id(link_job: str) -> str:
    """Tạo deterministic UUID từ link_job → cùng link luôn cùng ID."""
    return str(uuid.uuid5(_UUID_NAMESPACE, link_job))


class QdrantManager:
    """Quản lý toàn bộ thao tác với Qdrant collection."""

    # Các field cần tạo keyword index để hỗ trợ filter
    INDEXED_FIELDS = [
        "link_job",
        "salary",
        "experience",
        "level",
        "work_type",
        "loai_job",
        "xa_phuong",
        "company_field",
        "location",
    ]

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        collection_name: str | None = None,
    ):
        self._client = QdrantClient(
            url=url or config.QDRANT_URL,
            api_key=api_key or config.QDRANT_API_KEY,
        )
        self._collection = collection_name or config.QDRANT_COLLECTION_NAME

    def ensure_collection(self, vector_size: int = 1536) -> None:
        """Tạo collection nếu chưa tồn tại, kèm payload indexes."""
        collections = self._client.get_collections().collections
        exists = any(c.name == self._collection for c in collections)

        if not exists:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Created collection '%s'", self._collection)

            # Tạo payload indexes
            for field in self.INDEXED_FIELDS:
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            logger.info("Created %d payload indexes", len(self.INDEXED_FIELDS))
        else:
            logger.info("Collection '%s' already exists", self._collection)

    def get_existing_links(self) -> set[str]:
        """Scroll toàn bộ collection, trả về set link_job đã có."""
        existing = set()
        offset = None

        while True:
            results, offset = self._client.scroll(
                collection_name=self._collection,
                limit=1000,
                offset=offset,
                with_payload=["link_job"],
                with_vectors=False,
            )
            for point in results:
                link = point.payload.get("link_job")
                if link:
                    existing.add(link)

            if offset is None:
                break

        logger.info("Found %d existing points in Qdrant", len(existing))
        return existing

    def upsert_batch(self, points: list[PointStruct]) -> None:
        """Upsert một batch points vào collection."""
        self._client.upsert(
            collection_name=self._collection,
            points=points,
        )

    def delete_by_links(self, link_jobs: list[str]) -> None:
        """Xóa points theo danh sách link_job."""
        if not link_jobs:
            return

        point_ids = [job_to_point_id(link) for link in link_jobs]
        self._client.delete(
            collection_name=self._collection,
            points_selector=point_ids,
        )
        logger.info("Deleted %d points from Qdrant", len(point_ids))

    def get_collection_info(self):
        """Lấy thông tin collection (số points, status, ...)."""
        return self._client.get_collection(self._collection)

    def search(
        self,
        vector: list[float],
        limit: int = 10,
        query_filter: Filter | None = None,
    ) -> list:
        """Semantic search, trả về list ScoredPoint."""
        return self._client.query_points(
            collection_name=self._collection,
            query=vector,
            query_filter=query_filter,
            limit=limit,
        ).points

    def count_with_filter(self, scroll_filter: Filter | None = None) -> int:
        """Đếm số points khớp filter (rẻ — Qdrant có optimization riêng)."""
        return self._client.count(
            collection_name=self._collection,
            count_filter=scroll_filter,
            exact=True,
        ).count

    def scroll_with_filter(
        self,
        scroll_filter: Filter | None = None,
        limit: int = 200,
    ) -> list:
        """Scroll points khớp filter, trả list points (payload + id).

        Cap limit ≤ 500 để tránh response quá lớn.
        """
        points, _ = self._client.scroll(
            collection_name=self._collection,
            scroll_filter=scroll_filter,
            limit=min(limit, 500),
            with_payload=True,
            with_vectors=False,
        )
        return points
