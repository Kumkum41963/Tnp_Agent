"""
Vector Service — owns the ChromaDB client and collections.

Provides `upsert` and `query_similar` operations used by the Schema Agent.
Pure similarity-search utility — knows nothing about Excel, resumes, or students.
"""
from __future__ import annotations

from pathlib import Path

import chromadb
from loguru import logger

from app.config import settings
from app.services.embedding_service import embedding_service
from app.utils.constants import CHROMA_MASTER_FIELDS_COLLECTION


class VectorServiceError(Exception):
    """Raised on ChromaDB operation failures."""


class VectorService:
    """Manages ChromaDB collections and similarity queries."""

    def __init__(self) -> None:
        persist_dir = Path(settings.chroma_persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        logger.info(f"ChromaDB initialized at {persist_dir}")

    def _get_or_create_collection(
        self, name: str
    ) -> chromadb.Collection:
        return self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(
        self,
        collection_name: str,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict[str, str]] | None = None,
    ) -> None:
        """
        Upsert (insert or update) documents into a ChromaDB collection.

        Parameters
        ----------
        collection_name : ChromaDB collection to upsert into.
        ids             : Unique string IDs — one per text.
        texts           : Documents to embed and store.
        metadatas       : Optional metadata dicts — one per text.
        """
        if not ids:
            return
        collection = self._get_or_create_collection(collection_name)
        try:
            embeddings = embedding_service.embed(texts)
            collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas or [{} for _ in texts],
            )
            logger.debug(f"Upserted {len(ids)} items into collection '{collection_name}'")
        except Exception as exc:
            raise VectorServiceError(f"Upsert failed: {exc}") from exc

    def query_similar(
        self,
        collection_name: str,
        query_text: str,
        top_k: int = 5,
        where: dict[str, str] | None = None,
    ) -> list[dict[str, object]]:
        """
        Find the top-k most similar documents to `query_text`.

        Returns a list of dicts with keys: id, document, metadata, distance.
        Distance is cosine distance (0 = identical, 1 = orthogonal).
        """
        collection = self._get_or_create_collection(collection_name)
        try:
            query_vec = embedding_service.embed_query(query_text)
            n_results = min(top_k, collection.count())
            if n_results == 0:
                logger.warning(
                    f"Collection '{collection_name}' is empty. "
                    "Run vector_repository.index_master_fields() first."
                )
                return []
            results = collection.query(
                query_embeddings=[query_vec],
                n_results=n_results,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
            items: list[dict[str, object]] = []
            for i, doc_id in enumerate(results["ids"][0]):
                items.append({
                    "id": doc_id,
                    "document": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 1.0,
                })
            return items
        except Exception as exc:
            raise VectorServiceError(f"Similarity query failed: {exc}") from exc

    def collection_count(self, collection_name: str) -> int:
        """Return the number of items in a collection (0 if not yet created)."""
        try:
            col = self._client.get_collection(collection_name)
            return col.count()
        except Exception:
            return 0

    def delete_collection(self, collection_name: str) -> None:
        """Delete a collection entirely (use with caution — for re-indexing)."""
        try:
            self._client.delete_collection(collection_name)
            logger.info(f"Deleted ChromaDB collection '{collection_name}'")
        except Exception:
            pass  # Collection didn't exist; that's fine


# Singleton instance
vector_service = VectorService()
