"""
Schema Agent 

Two-stage approach:
1. Embedding similarity search in ChromaDB → top-k candidate Master DB fields per company column.
2. LLM is given the column name, sampled values, and the top-k candidates to pick the best
   match (or "none"), with a justification and confidence score. Returns strict JSON.

Inputs:  company column headers + sample rows + vector repository
Outputs: list[ColumnMapping]
"""
from __future__ import annotations

import json

from loguru import logger
from pydantic import BaseModel, Field

from app.config import settings
from app.models.column_mapping import ColumnMapping, MappingStatus
from app.repositories.vector_repository import vector_repository
from app.services.llm_service import LLMServiceError, llm_service

# ── Pydantic schema for LLM structured output ────────────────────────────────


class _ColumnMappingOutput(BaseModel):
    """Schema for the LLM's JSON response when mapping a single column."""
    matched_field: str | None = Field(
        description="The canonical Master DB field name, or null if no match."
    )
    inferred_type: str = Field(
        default="text",
        description="One of: text, number, date, email, phone, url, file",
    )
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


# ── System / User prompt templates ───────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a data schema mapping assistant for a college placement cell.
Given a company Excel column name, some sample cell values, and a shortlist of \
candidate fields from the TNP Master Database, decide which candidate best \
represents this column.

Rules:
- If one candidate is a clearly correct match, return it with high confidence.
- If none fit, return null for matched_field.
- NEVER invent a field name not in the candidate list.
- Respond ONLY with a valid JSON object. No prose, no markdown, no code fences.
"""

_USER_PROMPT_TEMPLATE = """\
Column name: "{column_name}"
Sample values: {sample_values}

Candidate Master DB fields (field_name: description — similarity_score):
{candidates}

Return a JSON object with this exact schema:
{{
  "matched_field": "<field_name or null>",
  "inferred_type": "<text|number|date|email|phone|url|file>",
  "confidence": <0.0 to 1.0>,
  "reason": "<brief explanation>"
}}
"""


class SchemaAgent:
    """
    Understands arbitrary company Excel schemas and produces ColumnMappings.
    """

    def __init__(self) -> None:
        self._threshold = settings.column_mapping_confidence_threshold
        self._top_k = 5

    def run(
        self,
        headers: list[str],
        sample_rows: list[dict[str, str]],
        columns_to_process: list[str] | None = None,
    ) -> list[ColumnMapping]:
        """
        Map company columns to Master DB fields.

        Parameters
        ----------
        headers             : All company column headers (in order).
        sample_rows         : Up to 5 sample rows from the company upload.
        columns_to_process  : If provided, only re-map these columns (for retry runs).

        Returns
        -------
        list[ColumnMapping] — one mapping per column in `headers`.
        """
        target_columns = set(columns_to_process or headers)
        # Ensure master fields are indexed
        vector_repository.index_master_fields()

        mappings: list[ColumnMapping] = []
        for header in headers:
            if header not in target_columns:
                mappings.append(ColumnMapping(
                    company_column=header,
                    status=MappingStatus.SKIPPED,
                ))
                continue
            mapping = self._map_column(header, sample_rows)
            mappings.append(mapping)

        mapped_count = sum(1 for m in mappings if m.status == MappingStatus.MAPPED)
        missing_count = sum(1 for m in mappings if m.status == MappingStatus.MISSING_FIELD)
        review_count = sum(1 for m in mappings if m.status == MappingStatus.NEEDS_REVIEW)
        logger.info(
            f"Schema Agent: {mapped_count} mapped, {missing_count} missing, "
            f"{review_count} need review out of {len(headers)} columns."
        )
        return mappings

    def _map_column(
        self,
        column_name: str,
        sample_rows: list[dict[str, str]],
    ) -> ColumnMapping:
        """Map a single column using embedding similarity + LLM reasoning."""
        # 1. Get sample values for this column
        sample_values = [
            row.get(column_name, "")
            for row in sample_rows[:5]
            if row.get(column_name, "").strip()
        ]

        # 2. Embedding similarity: get top-k candidate fields
        candidates = vector_repository.query_similar_fields(
            query_text=f"{column_name}: {' '.join(sample_values[:3])}",
            top_k=self._top_k,
        )

        if not candidates:
            logger.warning(
                f"No candidates from vector search for column '{column_name}'. "
                "Marking as missing_field."
            )
            return ColumnMapping(
                company_column=column_name,
                status=MappingStatus.MISSING_FIELD,
                confidence=0.0,
                reason="No similar Master DB fields found in vector index.",
            )

        # 3. LLM reasoning over the shortlist
        candidates_str = "\n".join(
            f"  - {c['metadata']['field_name']}: "
            f"{c['metadata'].get('description', '')} "
            f"(similarity={1 - float(str(c['distance'])):.2f})"
            for c in candidates
        )
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            column_name=column_name,
            sample_values=json.dumps(sample_values[:5]),
            candidates=candidates_str,
        )

        try:
            output = llm_service.generate_structured(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                schema=_ColumnMappingOutput,
                max_retries=settings.schema_agent_max_retries,
            )
        except LLMServiceError as exc:
            logger.error(f"Schema Agent LLM failed for column '{column_name}': {exc}")
            return ColumnMapping(
                company_column=column_name,
                status=MappingStatus.NEEDS_REVIEW,
                confidence=0.0,
                reason=f"LLM call failed after all retries: {exc}",
                review_candidates=[{
                    "field": c["metadata"].get("field_name"),
                    "description": c["metadata"].get("description"),
                    "similarity": 1 - float(str(c["distance"])),
                } for c in candidates],
            )

        # 4. Determine mapping status from confidence + matched_field
        if output.matched_field is None:
            status = MappingStatus.MISSING_FIELD
        elif output.confidence >= self._threshold:
            status = MappingStatus.MAPPED
        else:
            status = MappingStatus.NEEDS_REVIEW

        review_candidates = None
        if status == MappingStatus.NEEDS_REVIEW:
            review_candidates = [{
                "field": c["metadata"].get("field_name"),
                "description": c["metadata"].get("description"),
                "similarity": 1 - float(str(c["distance"])),
            } for c in candidates]

        logger.debug(
            f"Column '{column_name}' → '{output.matched_field}' "
            f"(confidence={output.confidence:.2f}, status={status.value})"
        )

        return ColumnMapping(
            company_column=column_name,
            mapped_field=output.matched_field,
            inferred_type=output.inferred_type,
            confidence=output.confidence,
            reason=output.reason,
            status=status,
            review_candidates=review_candidates,
        )

    def low_confidence_fraction(self, mappings: list[ColumnMapping]) -> float:
        """Return fraction of non-skipped mappings that need human review."""
        non_skipped = [m for m in mappings if m.status != MappingStatus.SKIPPED]
        if not non_skipped:
            return 0.0
        review_count = sum(1 for m in non_skipped if m.status == MappingStatus.NEEDS_REVIEW)
        return review_count / len(non_skipped)


# Singleton
schema_agent = SchemaAgent()
