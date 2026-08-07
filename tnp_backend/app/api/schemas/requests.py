"""
Pydantic request models for all API endpoints (§13 of the architecture doc).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class LoadMasterRequest(BaseModel):
    file_path: str = Field(
        default="data/master/master_database.xlsx",
        description="Path to the Master Database Excel/CSV file.",
    )


class ProcessRequest(BaseModel):
    company_name: str = Field(description="Name of the recruiting company.")
    submission_deadline: str = Field(
        description="ISO 8601 deadline string, e.g. '2026-08-15T18:00:00Z'"
    )
    company_file_path: str = Field(
        description="Path to the company's uploaded Excel template."
    )


class PopulateRequest(BaseModel):
    run_id: str = Field(description="Existing run ID to run schema+mapping+population on.")


class ValidateRequest(BaseModel):
    run_id: str = Field(description="Run ID to re-validate.")


class CorrectionItem(BaseModel):
    type: str = Field(description="'column_mapping' or 'identity_resolution'")
    # For column_mapping corrections
    company_column: str | None = None
    mapped_field: str | None = None
    # For identity_resolution corrections
    resume_file: str | None = None
    master_record_id: str | None = None


class ResumeRunRequest(BaseModel):
    corrections: list[CorrectionItem] = Field(default_factory=list)
