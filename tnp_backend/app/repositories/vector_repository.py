"""
Vector Repository — persistence-facing wrapper around vector_service's ChromaDB collections.

Owns collection lifecycle: create-if-not-exists, re-index on Master DB field catalogue changes.
This keeps vector_service itself a stateless similarity-query utility.
"""
from __future__ import annotations

from loguru import logger

from app.services.vector_service import vector_service
from app.utils.constants import CHROMA_MASTER_FIELDS_COLLECTION, MASTER_DB_FIELDS


class VectorRepository:
    """Manages the master_fields ChromaDB collection lifecycle."""

    def index_master_fields(self, force_reindex: bool = False) -> int:
        """
        Ensure the master_fields collection is populated with all known field descriptions.
        Safe to call multiple times — uses upsert semantics.

        Parameters
        ----------
        force_reindex : Delete the existing collection and rebuild from scratch.

        Returns
        -------
        Number of fields indexed.
        """
        if force_reindex:
            vector_service.delete_collection(CHROMA_MASTER_FIELDS_COLLECTION)
            logger.info("Deleted master_fields collection for forced re-index.")

        count_before = vector_service.collection_count(CHROMA_MASTER_FIELDS_COLLECTION)
        if count_before == len(MASTER_DB_FIELDS) and not force_reindex:
            logger.debug(
                f"master_fields collection already has {count_before} fields — skipping re-index."
            )
            return count_before

        ids = list(MASTER_DB_FIELDS.keys())
        texts = [
            f"{field}: {description}"
            for field, description in MASTER_DB_FIELDS.items()
        ]
        metadatas = [
            {"field_name": field, "description": description}
            for field, description in MASTER_DB_FIELDS.items()
        ]

        vector_service.upsert(
            collection_name=CHROMA_MASTER_FIELDS_COLLECTION,
            ids=ids,
            texts=texts,
            metadatas=metadatas,
        )
        count_after = vector_service.collection_count(CHROMA_MASTER_FIELDS_COLLECTION)
        logger.info(f"Indexed {count_after} Master DB fields into ChromaDB.")
        return count_after

    def query_similar_fields(
        self, query_text: str, top_k: int = 5
    ) -> list[dict[str, object]]:
        """
        Find the top-k Master DB fields most semantically similar to query_text.
        Used by the Schema Agent for candidate shortlisting.
        """
        return vector_service.query_similar(
            collection_name=CHROMA_MASTER_FIELDS_COLLECTION,
            query_text=query_text,
            top_k=top_k,
        )


# Singleton
vector_repository = VectorRepository()
