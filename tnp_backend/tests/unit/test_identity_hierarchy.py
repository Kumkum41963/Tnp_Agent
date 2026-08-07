"""
Unit tests for the deterministic identity hierarchy utility.
"""
from __future__ import annotations

import pytest

from app.models.master_record import MasterRecord
from app.utils.identity_hierarchy import run_deterministic_match


def _make_record(enrollment: str, phone: str | None = None, email: str | None = None) -> MasterRecord:
    return MasterRecord(
        enrollment_number=enrollment,
        name=f"Student {enrollment}",
        phone_number=phone,
        email=email,
    )


RECORDS = [
    _make_record("21CS045", phone="9876543210", email="alice@college.edu"),
    _make_record("21CS046", phone="9876543211", email="bob@college.edu"),
    _make_record("21EC010", phone="9876543212", email="carol@college.edu"),
]


class TestEnrollmentMatch:
    def test_exact_match(self) -> None:
        result = run_deterministic_match("21CS045", None, None, RECORDS)
        assert result.matched
        assert result.record is not None
        assert result.record.enrollment_number == "21CS045"
        assert result.method == "enrollment_number"

    def test_case_insensitive(self) -> None:
        result = run_deterministic_match("21cs045", None, None, RECORDS)
        assert result.matched
        assert result.record is not None
        assert result.record.enrollment_number == "21CS045"

    def test_no_match(self) -> None:
        result = run_deterministic_match("99XX999", None, None, RECORDS)
        assert not result.matched
        assert result.record is None


class TestPhoneMatch:
    def test_phone_match(self) -> None:
        result = run_deterministic_match(None, "9876543211", None, RECORDS)
        assert result.matched
        assert result.record is not None
        assert result.record.enrollment_number == "21CS046"
        assert result.method == "phone_number"

    def test_phone_with_country_code(self) -> None:
        result = run_deterministic_match(None, "+91-9876543210", None, RECORDS)
        assert result.matched


class TestEmailMatch:
    def test_email_match(self) -> None:
        result = run_deterministic_match(None, None, "carol@college.edu", RECORDS)
        assert result.matched
        assert result.record is not None
        assert result.record.enrollment_number == "21EC010"
        assert result.method == "email"

    def test_email_case_insensitive(self) -> None:
        result = run_deterministic_match(None, None, "CAROL@COLLEGE.EDU", RECORDS)
        assert result.matched


class TestFallthrough:
    def test_no_identifiers(self) -> None:
        result = run_deterministic_match(None, None, None, RECORDS)
        assert not result.matched
        assert result.record is None
        assert result.method is None
