"""
Pydantic models for per-student validation outcomes.
Produced by the Validation Agent + deterministic diff logic in report_service.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class DiffClassification(str, Enum):
    LIKELY_TYPO = "likely_typo"
    ACCEPTABLE_VARIATION = "acceptable_variation"
    REAL_MISMATCH = "real_mismatch"


class FieldClassification(BaseModel):
    """Classification of one field-level diff for a single student."""

    field: str
    master_value: str | None
    company_value: str | None
    classification: DiffClassification
    confidence: float = Field(ge=0.0, le=1.0)
    agent_classified: bool = Field(
        default=False,
        description="True if the Validation Agent classified this; False if deterministic.",
    )


class ValidationResult(BaseModel):
    """Per-student validation outcome for a single run."""

    enrollment_number: str
    passed: bool = Field(
        description="True if no real mismatches found after agent classification."
    )

    field_classifications: list[FieldClassification] = Field(default_factory=list)

    # Summary counts
    real_mismatch_count: int = 0
    likely_typo_count: int = 0
    acceptable_variation_count: int = 0

    # Completeness check
    missing_required_fields: list[str] = Field(
        default_factory=list,
        description="Company-required fields that are still empty after all collection.",
    )

    # Identity consistency
    identity_consistent: bool = True
    identity_issue: str | None = None

    # Review flags
    needs_human_review: bool = False
    review_reason: str | None = None
