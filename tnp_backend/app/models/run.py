"""
Pydantic model for a single "run" — one company drive's end-to-end pipeline execution.
Serialized to run_state.json after every node transition for debuggability/resumability.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    RUNNING = "running"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    COMPLETED = "completed"
    FAILED = "failed"


class Run(BaseModel):
    """Metadata + status for one pipeline run."""

    run_id: str
    company_name: str
    submission_deadline: str
    company_file_path: str

    status: RunStatus = RunStatus.RUNNING

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Progress tracking
    current_node: str | None = None
    schema_mapping_attempts: int = 0

    # Generated artifacts
    google_form_id: str | None = None
    google_form_url: str | None = None
    whatsapp_message: str | None = None

    # Output paths (relative to data/runs/{run_id}/outputs/)
    populated_db_path: str | None = None
    validation_report_path: str | None = None
    mismatch_report_path: str | None = None

    # Summary statistics (populated after completion)
    total_students: int = 0
    students_passed_validation: int = 0
    students_with_mismatches: int = 0
    students_flagged_for_review: int = 0
    missing_fields: list[str] = Field(default_factory=list)

    # Errors accumulated during the run
    errors: list[str] = Field(default_factory=list)
