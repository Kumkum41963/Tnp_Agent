"""
Unit tests for report_service deterministic diff computation.
"""
from __future__ import annotations

import pytest

from app.models.column_mapping import ColumnMapping, MappingStatus
from app.models.company_record import CompanyRecord
from app.models.master_record import MasterRecord
from app.services.report_service import (
    ReportService,
    classify_diffs_deterministically,
    compute_diffs,
)


def _mapping(company_col: str, master_field: str) -> ColumnMapping:
    return ColumnMapping(
        company_column=company_col,
        mapped_field=master_field,
        status=MappingStatus.MAPPED,
        confidence=0.95,
    )


def _master(enrollment: str, **kwargs: object) -> MasterRecord:
    return MasterRecord(enrollment_number=enrollment, name="Test Student", **kwargs)


def _company(enrollment: str, **data: object) -> CompanyRecord:
    return CompanyRecord(
        enrollment_number=enrollment,
        data={k: str(v) for k, v in data.items()},
    )


class TestComputeDiffs:
    def test_no_diff_when_values_match(self) -> None:
        master = _master("21CS045", cgpa=8.5)
        company = _company("21CS045", CGPA="8.5")
        mappings = [_mapping("CGPA", "cgpa")]
        diffs = compute_diffs(master, company, mappings)
        assert diffs == []

    def test_detects_diff(self) -> None:
        master = _master("21CS045", cgpa=8.5)
        company = _company("21CS045", CGPA="8.7")
        mappings = [_mapping("CGPA", "cgpa")]
        diffs = compute_diffs(master, company, mappings)
        assert len(diffs) == 1
        assert diffs[0]["field"] == "cgpa"


class TestClassifyDiffs:
    def test_alphanum_same_is_acceptable_variation(self) -> None:
        diffs = [{"field": "branch", "master_value": "CS", "company_value": "C.S."}]
        classified, ambiguous = classify_diffs_deterministically(diffs)
        assert len(classified) == 1
        assert classified[0].classification.value == "acceptable_variation"
        assert len(ambiguous) == 0

    def test_empty_vs_value_is_real_mismatch(self) -> None:
        diffs = [{"field": "cgpa", "master_value": None, "company_value": "9.0"}]
        classified, ambiguous = classify_diffs_deterministically(diffs)
        assert classified[0].classification.value == "real_mismatch"

    def test_clearly_different_goes_to_ambiguous(self) -> None:
        diffs = [{"field": "cgpa", "master_value": "8.5", "company_value": "9.0"}]
        classified, ambiguous = classify_diffs_deterministically(diffs)
        assert len(ambiguous) == 1
