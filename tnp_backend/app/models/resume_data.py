"""
Pydantic model for data extracted from a single resume PDF.
Produced by the PDF Service and enriched by the Resume Extract Identity Agent.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ResumeData(BaseModel):
    """
    Fields extracted from a resume PDF, plus identity resolution metadata.
    All extracted fields are nullable — PDFs are not always well-structured.
    """

    # Source tracking
    resume_file: str = Field(description="Filename of the source resume PDF.")

    # Form-declared identity (from the linked Google Form response)
    form_declared_enrollment: str | None = None
    form_declared_name: str | None = None

    # Extracted from PDF text
    extracted_name: str | None = None
    extracted_phone: str | None = None
    extracted_email: str | None = None
    extracted_enrollment: str | None = None

    # Resolution result
    resolved_master_record_id: str | None = Field(
        default=None,
        description="Enrollment number of the matched Master DB record.",
    )
    resolution_method: str | None = Field(
        default=None,
        description="How identity was resolved: enrollment_number | phone_number | email | ai",
    )
    resolution_confidence: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    resolution_reason: str | None = Field(
        default=None,
        description="Human-readable explanation from the AI agent (stored for audit).",
    )

    # Review / failure flags
    needs_human_review: bool = False
    resolution_failed: bool = False
    review_reason: str | None = None
