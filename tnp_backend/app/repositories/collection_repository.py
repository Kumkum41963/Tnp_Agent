"""
Collection Repository — read interface over Google Form responses pulled into
the linked Google Sheet via google_service.

Normalizes raw sheet rows into typed response objects keyed by enrollment number,
regardless of the dynamic question order generated in FR-7.
"""
from __future__ import annotations

from loguru import logger

from app.services.google_service import google_service


class CollectionRepository:
    """Reads and normalizes Google Form responses for a specific run's form."""

    def __init__(self, run_id: str, form_id: str) -> None:
        self._run_id = run_id
        self._form_id = form_id

    def fetch_responses(self) -> list[dict[str, str]]:
        """
        Pull all current responses from the Google Sheet linked to this form.
        Returns normalized dicts keyed by field name (not column index).

        Each response dict is guaranteed to contain:
            "enrollment_number" (str)
            "name"              (str)
            + any other submitted fields
        """
        raw = google_service.get_form_responses(self._form_id)
        normalized = self._normalize(raw)
        logger.info(
            f"[{self._run_id}] Fetched {len(normalized)} form responses from Google Sheet."
        )
        return normalized

    def get_responded_enrollments(self) -> set[str]:
        """Return the set of enrollment numbers that have already responded."""
        responses = self.fetch_responses()
        return {
            r["enrollment_number"].strip().upper()
            for r in responses
            if r.get("enrollment_number")
        }

    def get_pending_enrollments(
        self, all_enrollments: list[str]
    ) -> list[str]:
        """Return enrollments that haven't responded yet."""
        responded = self.get_responded_enrollments()
        return [e for e in all_enrollments if e.upper() not in responded]

    @staticmethod
    def _normalize(raw_responses: list[dict[str, str]]) -> list[dict[str, str]]:
        """
        Normalize raw Sheet rows to use canonical field names where possible.
        The form always includes Enrollment Number and Student Name as the first
        two questions, so we detect them by common name patterns.
        """
        normalized = []
        for row in raw_responses:
            norm: dict[str, str] = {}
            for key, value in row.items():
                clean_key = key.strip().lower().replace(" ", "_").replace("-", "_")
                # Map common form header names to canonical fields
                if clean_key in ("enrollment_number", "enroll_no", "roll_no", "reg_no"):
                    norm["enrollment_number"] = str(value).strip().upper()
                elif clean_key in ("student_name", "name", "full_name"):
                    norm["name"] = str(value).strip()
                else:
                    norm[clean_key] = str(value).strip()
            normalized.append(norm)
        return normalized
