"""
 Shared pipeline state passed through every LangGraph node.
 Each node reads from it and updates it.
 The state is saved after every node, making the workflow easy to resume or replay.
"""
from __future__ import annotations

from typing import Literal

from typing_extensions import TypedDict

from app.models.column_mapping import ColumnMapping
from app.models.master_record import MasterRecord
from app.models.resume_data import ResumeData
from app.models.validation_result import ValidationResult


class PipelineState(TypedDict, total=False):
    # ── Run metadata ─────────────────────────────────────────────────────────
    run_id: str
    company_name: str
    submission_deadline: str

    # ── Inputs ───────────────────────────────────────────────────────────────
    master_file_path: str
    master_records: list[MasterRecord]
    company_file_path: str
    company_headers: list[str]      # Raw headers from company upload
    company_sample_rows: list[dict[str, str]]  # First 5 rows for Schema Agent

    # ── Schema + mapping ─────────────────────────────────────────────────────
    column_mappings: list[ColumnMapping]
    schema_mapping_attempts: int
    schema_needs_review: bool

    # ── Population ───────────────────────────────────────────────────────────
    missing_fields: list[str]       # Company-required fields not in Master DB

    # ── Form + collection ────────────────────────────────────────────────────
    google_form_id: str | None
    google_form_url: str | None
    whatsapp_message: str | None
    form_responses: list[dict[str, str]]

    # ── Resumes ──────────────────────────────────────────────────────────────
    resume_files: list[str]          # Local paths to downloaded resume PDFs
    resolved_identities: list[ResumeData]
    identity_resolution_attempts: dict[str, int]  # resume_file → attempt count

    # ── Validation ───────────────────────────────────────────────────────────
    validation_results: list[ValidationResult]

    # ── Outputs ──────────────────────────────────────────────────────────────
    populated_db_path: str | None
    validation_report_path: str | None
    mismatch_report_path: str | None

    # ── Control ──────────────────────────────────────────────────────────────
    status: Literal["running", "awaiting_human_review", "completed", "failed"]
    current_node: str
    errors: list[str]
