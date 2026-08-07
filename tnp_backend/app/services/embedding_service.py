"""
Embedding Service — generates vector embeddings for text.

Expose a single `embed(texts)` method. The caller (vector_service) does
not need to know which embedding backend is active.
"""
from __future__ import annotations

from loguru import logger

from app.config import settings


class EmbeddingServiceError(Exception):
    """Raised when embedding generation fails."""


class EmbeddingService:
    """Generates embeddings via the Ollama embedding endpoint."""

    def __init__(self) -> None:
        self._model = settings.ollama_embedding_model
        self._base_url = settings.ollama_base_url
        self._client: object | None = None

    def _get_client(self) -> object:
        """Lazy-initialize the OllamaEmbeddings client."""
        if self._client is None:
            try:
                from langchain_ollama import OllamaEmbeddings

                self._client = OllamaEmbeddings(
                    base_url=self._base_url,
                    model=self._model,
                )
                logger.info(
                    f"EmbeddingService initialized with model={self._model} "
                    f"at {self._base_url}"
                )
            except Exception as exc:
                raise EmbeddingServiceError(
                    f"Failed to initialize OllamaEmbeddings: {exc}\n"
                    f"Ensure your Ollama server is running at {self._base_url} "
                    f"and the model '{self._model}' is pulled "
                    f"(run: ollama pull {self._model})."
                ) from exc
        return self._client  # type: ignore[return-value]

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of strings. Returns one vector per input text.
        Raises EmbeddingServiceError on failure.
        """
        if not texts:
            return []
        client = self._get_client()
        try:
            from langchain_ollama import OllamaEmbeddings

            assert isinstance(client, OllamaEmbeddings)
            vectors = client.embed_documents(texts)
            logger.debug(f"Embedded {len(texts)} texts → {len(vectors)} vectors")
            return vectors
        except Exception as exc:
            raise EmbeddingServiceError(f"Embedding failed: {exc}") from exc

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string (optimized path in some backends)."""
        client = self._get_client()
        try:
            from langchain_ollama import OllamaEmbeddings

            assert isinstance(client, OllamaEmbeddings)
            return client.embed_query(text)
        except Exception as exc:
            raise EmbeddingServiceError(f"Query embedding failed: {exc}") from exc


# Singleton instance
embedding_service = EmbeddingService()
