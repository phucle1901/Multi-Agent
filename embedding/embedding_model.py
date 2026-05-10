"""Gọi OpenAI Embedding API.

Hỗ trợ batch embedding với retry tự động (built-in trong OpenAI SDK).
"""

from openai import OpenAI

from embedding import config


class EmbeddingModel:
    """Wrapper cho OpenAI Embedding API."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
    ):
        self._client = OpenAI(api_key=api_key or config.OPENAI_API_KEY)
        self._model = model_name or config.EMBEDDING_MODEL_NAME

    @property
    def dimension(self) -> int:
        return 1536

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed danh sách text, trả về list vectors.

        OpenAI SDK tự xử lý retry cho 429/5xx.
        """
        response = self._client.embeddings.create(
            input=texts,
            model=self._model,
        )
        return [item.embedding for item in response.data]
