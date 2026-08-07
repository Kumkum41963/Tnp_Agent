"""
Master Repository — read-only interface over the loaded Master Database.

Provides lookups by enrollment number, phone, and email,
backing the FR-10 deterministic identity hierarchy directly.
Loaded once per run and cached in memory.
"""
from __future__ import annotations

from loguru import logger

from app.models.master_record import MasterRecord
from app.services.excel_service import excel_service
from app.utils.identity_hierarchy import normalize_email, normalize_enrollment, normalize_phone


class MasterRepositoryError(Exception):
    """Raised on Master Repository access errors."""


class MasterRepository:
    """In-memory, read-only access to the Master Database."""

    def __init__(self) -> None:
        self._records: list[MasterRecord] = []
        self._by_enrollment: dict[str, MasterRecord] = {}
        self._by_phone: dict[str, list[MasterRecord]] = {}
        self._by_email: dict[str, list[MasterRecord]] = {}
        self._loaded = False

    def load(self, file_path: str) -> int:
        """
        Load (or reload) the Master Database from an Excel/CSV file.
        Returns the number of records loaded.
        """
        self._records = excel_service.load_master_database(file_path)
        self._build_indices()
        self._loaded = True
        logger.info(f"Master Repository loaded with {len(self._records)} records.")
        return len(self._records)

    def load_from_records(self, records: list[MasterRecord]) -> None:
        """Load directly from a pre-parsed list (used in tests / LangGraph nodes)."""
        self._records = records
        self._build_indices()
        self._loaded = True

    def is_loaded(self) -> bool:
        return self._loaded

    def record_count(self) -> int:
        return len(self._records)

    def list_all(self) -> list[MasterRecord]:
        self._require_loaded()
        return list(self._records)

    def get_by_enrollment(self, enrollment_number: str) -> MasterRecord | None:
        self._require_loaded()
        return self._by_enrollment.get(normalize_enrollment(enrollment_number) or "")

    def get_by_phone(self, phone: str) -> list[MasterRecord]:
        """Returns all records with this phone number (usually 0 or 1)."""
        self._require_loaded()
        return self._by_phone.get(normalize_phone(phone) or "", [])

    def get_by_email(self, email: str) -> list[MasterRecord]:
        """Returns all records with this email (usually 0 or 1)."""
        self._require_loaded()
        return self._by_email.get(normalize_email(email) or "", [])

    def _build_indices(self) -> None:
        """Build in-memory lookup indices for fast deterministic matching."""
        self._by_enrollment = {}
        self._by_phone = {}
        self._by_email = {}

        for record in self._records:
            # Enrollment number (must be unique — warn if not)
            norm_enr = normalize_enrollment(record.enrollment_number)
            if norm_enr:
                if norm_enr in self._by_enrollment:
                    logger.warning(
                        f"Duplicate enrollment_number '{norm_enr}' in Master DB. "
                        "Only the first occurrence is indexed."
                    )
                else:
                    self._by_enrollment[norm_enr] = record

            # Phone
            norm_phone = normalize_phone(record.phone_number)
            if norm_phone:
                self._by_phone.setdefault(norm_phone, []).append(record)

            # Email
            norm_email = normalize_email(record.email)
            if norm_email:
                self._by_email.setdefault(norm_email, []).append(record)

    def _require_loaded(self) -> None:
        if not self._loaded:
            raise MasterRepositoryError(
                "Master Database not loaded. Call POST /api/v1/master/load first."
            )


# Singleton — shared across the application lifetime
master_repository = MasterRepository()
