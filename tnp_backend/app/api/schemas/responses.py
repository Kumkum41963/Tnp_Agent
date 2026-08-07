"""
Pydantic response models for all API endpoints
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class LoadMasterResponse(BaseModel):
    status: str
    record_count: int
    loaded_at: str


class ProcessResponse(BaseModel):
    run_id: str
    status: str


class ColumnMappingSummary(BaseModel):
    company_column: str
    mapped_field: str | None
    confidence: float
    status: str


class PopulateResponse(BaseModel):
    run_id: str
    column_mappings: list[ColumnMappingSummary]
    missing_fields: list[str]


class FormStatusResponse(BaseModel):
    run_id: str
    google_form_url: str | None
    google_form_id: str | None
    whatsapp_message: str | None


class ValidateResponse(BaseModel):
    run_id: str
    status: str
    mismatch_count: int
    flagged_for_review: int


class ReportResponse(BaseModel):
    run_id: str
    populated_database_path: str | None
    validation_report_path: str | None
    mismatch_report_path: str | None


class ResumeRunResponse(BaseModel):
    run_id: str
    status: str


class HealthResponse(BaseModel):
    status: str
    version: str = "1.0.0"
    ollama_base_url: str
    google_integration_enabled: bool
