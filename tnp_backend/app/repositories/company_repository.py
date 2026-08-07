"""
Company Repository — per-run read/write interface over the in-progress Company Database.

Starts as the raw company upload rows, progressively enriched:
  1. After schema mapping + population → company_records are partially filled
  2. After form responses arrive → missing_field_values filled
  3. After resume parsing → resume data and resolved identity attached
"""
from __future__ import annotations

from loguru import logger

from app.models.column_mapping import ColumnMapping, MappingStatus
from app.models.company_record import CompanyRecord, RecordStatus
from app.models.master_record import MasterRecord
from app.models.resume_data import ResumeData


class CompanyRepositoryError(Exception):
    """Raised on Company Repository access errors."""


class CompanyRepository:
    """In-memory store for the in-progress Company Database for one run."""

    def __init__(self) -> None:
        self._records: dict[str, CompanyRecord] = {}  # enrollment_number → record
        self._run_id: str | None = None
        self._company_headers: list[str] = []

    def initialize(
        self,
        run_id: str,
        company_headers: list[str],
        raw_rows: list[dict[str, str]],
    ) -> None:
        """
        Initialize with raw company upload rows.
        Creates one CompanyRecord per row (enrollment_number determined later via mapping).
        """
        self._run_id = run_id
        self._company_headers = company_headers
        self._records = {}

        # We don't yet know which column is enrollment_number — store raw data
        # keyed temporarily by row index; populate_from_master will re-key by enrollment
        self._raw_rows = raw_rows
        logger.info(f"[{run_id}] CompanyRepository initialized with {len(raw_rows)} raw rows.")

    def populate_from_master(
        self,
        master_records: list[MasterRecord],
        column_mappings: list[ColumnMapping],
    ) -> int:
        """
        Fill company records for each Master DB student using confident column mappings.
        Returns the count of records populated.
        """
        # Find the company column that maps to enrollment_number
        enrollment_col: str | None = None
        for mapping in column_mappings:
            if (
                mapping.mapped_field == "enrollment_number"
                and mapping.status == MappingStatus.MAPPED
            ):
                enrollment_col = mapping.company_column
                break

        self._records = {}
        populated = 0

        for master in master_records:
            data: dict[str, str | None] = {}

            for mapping in column_mappings:
                if mapping.status != MappingStatus.MAPPED or mapping.mapped_field is None:
                    continue
                master_flat = master.to_flat_dict()
                value = master_flat.get(mapping.mapped_field)
                data[mapping.company_column] = str(value) if value is not None else None

            record = CompanyRecord(
                enrollment_number=master.enrollment_number,
                status=RecordStatus.POPULATED,
                data=data,
            )
            self._records[master.enrollment_number] = record
            populated += 1

        logger.info(
            f"[{self._run_id}] Populated {populated} company records from Master DB."
        )
        return populated

    def merge_form_responses(
        self,
        responses: list[dict[str, str]],
        missing_fields: list[str],
    ) -> int:
        """
        Merge Google Form responses into company records.
        Responses must contain enrollment_number as the identity key.
        Returns the count of records updated.
        """
        merged = 0
        for response in responses:
            enrollment = response.get("enrollment_number", "").strip().upper()
            if not enrollment:
                logger.warning("Form response missing enrollment_number — skipping.")
                continue
            record = self._records.get(enrollment)
            if record is None:
                logger.warning(
                    f"Form response for unknown enrollment {enrollment} — skipping."
                )
                continue
            for field in missing_fields:
                if field in response:
                    record.missing_field_values[field] = response[field]
            record.status = RecordStatus.COMPLETE
            merged += 1
        logger.info(f"[{self._run_id}] Merged {merged} form responses.")
        return merged

    def attach_resume_data(self, resume_data: ResumeData) -> bool:
        """
        Attach resolved resume data to the matching company record.
        Returns True if the record was found and updated.
        """
        enrollment = resume_data.resolved_master_record_id
        if not enrollment:
            logger.warning(
                f"Cannot attach resume {resume_data.resume_file} — no resolved identity."
            )
            return False
        record = self._records.get(enrollment.upper())
        if record is None:
            logger.warning(
                f"Resolved enrollment {enrollment} not in company records — skipping."
            )
            return False
        record.resume_file = resume_data.resume_file
        record.resume_resolved_identity = resume_data.resolved_master_record_id
        record.resume_resolution_confidence = resume_data.resolution_confidence
        record.resume_resolution_method = resume_data.resolution_method
        if resume_data.needs_human_review:
            record.status = RecordStatus.NEEDS_REVIEW
            record.review_reason = resume_data.review_reason
        return True

    def list_all(self) -> list[CompanyRecord]:
        return list(self._records.values())

    def get(self, enrollment_number: str) -> CompanyRecord | None:
        return self._records.get(enrollment_number.upper())

    def company_headers(self) -> list[str]:
        return list(self._company_headers)

    def to_output_rows(
        self, column_mappings: list[ColumnMapping]
    ) -> list[dict[str, str | None]]:
        """
        Export all records as dicts keyed by original company column headers,
        ready to be written by the Excel Service.
        """
        rows: list[dict[str, str | None]] = []
        for record in self._records.values():
            row: dict[str, str | None] = {}
            for header in self._company_headers:
                # Check main data first, then missing_field_values
                if header in record.data:
                    row[header] = record.data[header]
                else:
                    # Look up by mapped field name
                    for mapping in column_mappings:
                        if (
                            mapping.company_column == header
                            and mapping.mapped_field in record.missing_field_values
                        ):
                            row[header] = record.missing_field_values[mapping.mapped_field]
                            break
                    else:
                        row[header] = record.missing_field_values.get(header)
            rows.append(row)
        return rows


# Factory function — a new instance is created per run, not a global singleton
def new_company_repository() -> CompanyRepository:
    return CompanyRepository()
