"""
Pydantic model for a single company column → Master DB field mapping.
Produced by the Schema Agent.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class MappingStatus(str, Enum):
    MAPPED = "mapped"               # Confident match to a Master DB field
    MISSING_FIELD = "missing_field" # Unmapped; needs collection via Google Form
    NEEDS_REVIEW = "needs_review"   # Low confidence; human must decide
    SKIPPED = "skipped"             # Column intentionally ignored (e.g. row index)


class ColumnMapping(BaseModel):
    """
    Maps one company column to either a Master DB field or marks it as missing/review.
    """

    company_column: str = Field(description="Raw column header from the company's Excel file.")
    mapped_field: str | None = Field(
        default=None,
        description="The canonical Master DB field name this column maps to, if any.",
    )
    inferred_type: str = Field(
        default="text",
        description="Inferred data type: text | number | date | email | phone | url | file",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score (0–1) from the Schema Agent.",
    )
    reason: str | None = Field(
        default=None,
        description="Short justification from the Schema Agent.",
    )
    status: MappingStatus = Field(default=MappingStatus.NEEDS_REVIEW)

    # Populated only for fields flagged for human review
    review_candidates: list[dict[str, object]] | None = Field(
        default=None,
        description="Top-k candidate Master DB fields offered to human reviewer.",
    )

    def is_resolved(self) -> bool:
        """True if this mapping is either confidently mapped or confirmed missing."""
        return self.status in {MappingStatus.MAPPED, MappingStatus.MISSING_FIELD}
