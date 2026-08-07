"""
Deterministic identity-matching hierarchy (FR-10).

Resolves a parsed resume to a single student in the Master Database using
a strict priority chain:
  1. Enrollment Number  (highest trust, most specific)
  2. Phone Number       (uniquely identifies if it appears in exactly one record)
  3. Email              (uniquely identifies if it appears in exactly one record)
  4. AI fallback        (handled by the Resume Extract Identity Agent, not here)

Returns the matched MasterRecord if a unique deterministic match is found,
or None to signal that the AI agent must be invoked.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from loguru import logger

from app.models.master_record import MasterRecord
from app.utils.constants import ENROLLMENT_NUMBER_PATTERN


@dataclass
class DeterministicMatchResult:
    """Result from the deterministic identity hierarchy."""
    matched: bool
    record: MasterRecord | None
    method: str | None  # "enrollment_number" | "phone_number" | "email"
    ambiguous: bool = False  # True if >1 candidate found (still returns None)
    candidates: list[MasterRecord] | None = None  # The ambiguous candidates


def normalize_phone(phone: str | None) -> str | None:
    """Strip non-digit chars, keep last 10 digits for comparison."""
    if phone is None:
        return None
    digits = re.sub(r"\D", "", phone)
    return digits[-10:] if len(digits) >= 10 else None


def normalize_email(email: str | None) -> str | None:
    """Lowercase and strip whitespace."""
    if email is None:
        return None
    return email.strip().lower()


def normalize_enrollment(enrollment: str | None) -> str | None:
    """Uppercase and strip whitespace."""
    if enrollment is None:
        return None
    return enrollment.strip().upper()


def extract_enrollment_from_text(text: str) -> str | None:
    """Regex-extract the first enrollment-number-like token from raw text."""
    match = re.search(ENROLLMENT_NUMBER_PATTERN, text.upper())
    return match.group(0) if match else None


def run_deterministic_match(
    enrollment: str | None,
    phone: str | None,
    email: str | None,
    all_records: list[MasterRecord],
) -> DeterministicMatchResult:
    """
    Run the three-step deterministic matching hierarchy.

    Parameters
    ----------
    enrollment : Enrollment number extracted from the resume (may be None).
    phone      : Phone number extracted from the resume (may be None).
    email      : Email extracted from the resume (may be None).
    all_records: Full list of Master Database records to search.

    Returns
    -------
    DeterministicMatchResult — check `.matched` first, then `.record`.
    """
    # ── Step 1: Enrollment Number ──────────────────────────────────────────
    norm_enrollment = normalize_enrollment(enrollment)
    if norm_enrollment:
        matches = [
            r for r in all_records
            if normalize_enrollment(r.enrollment_number) == norm_enrollment
        ]
        if len(matches) == 1:
            logger.debug(
                f"Deterministic match via enrollment_number: {norm_enrollment}"
            )
            return DeterministicMatchResult(
                matched=True,
                record=matches[0],
                method="enrollment_number",
            )
        if len(matches) > 1:
            logger.warning(
                f"Ambiguous enrollment_number match ({norm_enrollment}) → "
                f"{len(matches)} records, falling through to phone."
            )

    # ── Step 2: Phone Number ───────────────────────────────────────────────
    norm_phone = normalize_phone(phone)
    if norm_phone:
        matches = [
            r for r in all_records
            if normalize_phone(r.phone_number) == norm_phone
        ]
        if len(matches) == 1:
            logger.debug(f"Deterministic match via phone_number: {norm_phone}")
            return DeterministicMatchResult(
                matched=True,
                record=matches[0],
                method="phone_number",
            )
        if len(matches) > 1:
            logger.warning(
                f"Ambiguous phone_number match → {len(matches)} records, "
                "falling through to email."
            )

    # ── Step 3: Email ──────────────────────────────────────────────────────
    norm_email = normalize_email(email)
    if norm_email:
        matches = [
            r for r in all_records
            if normalize_email(r.email) == norm_email
        ]
        if len(matches) == 1:
            logger.debug(f"Deterministic match via email: {norm_email}")
            return DeterministicMatchResult(
                matched=True,
                record=matches[0],
                method="email",
            )
        if len(matches) > 1:
            return DeterministicMatchResult(
                matched=False,
                record=None,
                method="email",
                ambiguous=True,
                candidates=matches,
            )

    # ── All methods failed → route to AI agent ─────────────────────────────
    logger.info(
        "Deterministic hierarchy exhausted with no unique match. "
        "Routing to Resume Extract Identity Agent."
    )
    return DeterministicMatchResult(
        matched=False,
        record=None,
        method=None,
        ambiguous=False,
    )
