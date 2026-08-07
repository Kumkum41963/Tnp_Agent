"""
Pydantic model for one row of the Company Database (in-progress, per-run).
Starts as the raw upload row; progressively enriched by the pipeline.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RecordStatus(str, Enum):
    PENDING = "pending"           # Not yet populated
    POPULATED = "populated"       # Filled from Master DB; awaiting form data
    COMPLETE = "complete"         # All fields filled (master + form + resume)
    INCOMPLETE = "incomplete"     # Some required fields still missing after collection
    NEEDS_REVIEW = "needs_review" # Identity or validation issue flagged


class CompanyRecord(BaseModel):
    """
    One row in the Company Database for a specific run.
    The `data` dict maps company column headers to their current values.
    """

    enrollment_number: str = Field(description="Identity anchor from Master DB.")
    status: RecordStatus = Field(default=RecordStatus.PENDING)

    # Company template data: {company_column_name → value}
    data: dict[str, str | None] = Field(default_factory=dict)

    # Which fields are still missing (from the missing_fields list)
    missing_field_values: dict[str, str | None] = Field(
        default_factory=dict,
        description="Values for company-required fields not in the Master DB, "
                    "collected via Google Form.",
    )

    # Resume resolution metadata
    resume_file: str | None = None
    resume_resolved_identity: str | None = None  # master_record_id
    resume_resolution_confidence: float | None = None
    resume_resolution_method: str | None = None  # enrollment_number | phone | email | ai

    # Review flags
    review_reason: str | None = None
