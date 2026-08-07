"""
Report Service — builds the three final output artifacts.

Responsibilities:
1. Compute deterministic field-by-field diffs between Company DB and Master DB.
2. Invoke the Validation Agent only for ambiguous diffs.
3. Assemble per-student ValidationResult objects.
4. Write three Excel artifacts:
   - Populated Company Database (original column order)
   - Validation Report (per-student pass/fail with reasons)
   - Mismatch Report (focused diff view of disagreeing fields only)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from loguru import logger

from app.models.column_mapping import ColumnMapping, MappingStatus
from app.models.company_record import CompanyRecord
from app.models.master_record import MasterRecord
from app.models.validation_result import (
    DiffClassification,
    FieldClassification,
    ValidationResult,
)
from app.services.excel_service import excel_service
from app.utils.constants import (
    OUTPUT_MISMATCH_REPORT,
    OUTPUT_POPULATED_DB,
    OUTPUT_VALIDATION_REPORT,
)


# Fields that require exact match (no "acceptable variation" tolerance)
STRICT_MATCH_FIELDS = {"enrollment_number", "name", "cgpa"}


def _normalize_value(v: object) -> str:
    """Normalize a value for comparison: lowercase, strip whitespace."""
    if v is None:
        return ""
    return str(v).strip().lower()


def compute_diffs(
    master: MasterRecord,
    company: CompanyRecord,
    column_mappings: list[ColumnMapping],
) -> list[dict[str, str | None]]:
    """
    Compute field-by-field diffs between a Master record and a Company record.
    Only checks fields that are confidently mapped (MAPPED status).

    Returns a list of {"field", "master_value", "company_value"} for each
    field where values differ after normalization.
    """
    diffs: list[dict[str, str | None]] = []
    master_flat = master.to_flat_dict()

    for mapping in column_mappings:
        if mapping.status != MappingStatus.MAPPED or mapping.mapped_field is None:
            continue

        field = mapping.mapped_field
        master_val = master_flat.get(field)
        company_val = company.data.get(mapping.company_column)

        # Skip if both are empty
        if not master_val and not company_val:
            continue

        if _normalize_value(master_val) != _normalize_value(company_val):
            diffs.append({
                "field": field,
                "master_value": str(master_val) if master_val is not None else None,
                "company_value": str(company_val) if company_val is not None else None,
            })

    return diffs


def classify_diffs_deterministically(
    diffs: list[dict[str, str | None]],
) -> tuple[list[FieldClassification], list[dict[str, str | None]]]:
    """
    Deterministically classify diffs that are obviously clear-cut.
    Returns (classified_list, remaining_ambiguous).

    Clear-cut cases:
    - Identical after full normalization → skip (already handled in compute_diffs)
    - Identical after stripping punctuation + case → acceptable_variation
    - One is None/empty and the other is not → real_mismatch
    """
    classified: list[FieldClassification] = []
    ambiguous: list[dict[str, str | None]] = []

    for diff in diffs:
        master_val = diff["master_value"]
        company_val = diff["company_value"]
        field = diff["field"]

        # One side is empty
        if not master_val or not company_val:
            classified.append(FieldClassification(
                field=field,
                master_value=master_val,
                company_value=company_val,
                classification=DiffClassification.REAL_MISMATCH,
                confidence=0.95,
                agent_classified=False,
            ))
            continue

        # Strip all non-alphanumeric and compare
        def alphanum(s: str) -> str:
            import re
            return re.sub(r"[^a-z0-9]", "", s.lower())

        if alphanum(master_val) == alphanum(company_val):
            classified.append(FieldClassification(
                field=field,
                master_value=master_val,
                company_value=company_val,
                classification=DiffClassification.ACCEPTABLE_VARIATION,
                confidence=0.9,
                agent_classified=False,
            ))
            continue

        # Pass the rest to the AI agent
        ambiguous.append(diff)

    return classified, ambiguous


class ReportService:
    """Builds validation results and final output artifacts."""

    def build_validation_results(
        self,
        master_records: list[MasterRecord],
        company_records: list[CompanyRecord],
        column_mappings: list[ColumnMapping],
        validation_agent: object | None = None,  # Injected to avoid circular imports
    ) -> list[ValidationResult]:
        """
        Run the full validation pipeline for all students.
        Optionally invokes the Validation Agent for ambiguous diffs.
        """
        master_by_id = {r.enrollment_number: r for r in master_records}
        results: list[ValidationResult] = []

        for company_record in company_records:
            master = master_by_id.get(company_record.enrollment_number)
            if master is None:
                # Student in Company DB but not in Master DB
                results.append(ValidationResult(
                    enrollment_number=company_record.enrollment_number,
                    passed=False,
                    identity_consistent=False,
                    identity_issue="Enrollment number not found in Master Database",
                    needs_human_review=True,
                    review_reason="Student in company file has no Master DB record",
                ))
                continue

            diffs = compute_diffs(master, company_record, column_mappings)
            det_classified, ambiguous = classify_diffs_deterministically(diffs)

            agent_classified: list[FieldClassification] = []
            if ambiguous and validation_agent is not None:
                try:
                    agent_classified = validation_agent.classify(  # type: ignore[attr-defined]
                        enrollment_number=company_record.enrollment_number,
                        diffs=ambiguous,
                    )
                except Exception as exc:
                    logger.warning(
                        f"Validation Agent failed for {company_record.enrollment_number}: {exc}. "
                        "Defaulting all ambiguous diffs to real_mismatch."
                    )
                    agent_classified = [
                        FieldClassification(
                            field=d["field"],
                            master_value=d["master_value"],
                            company_value=d["company_value"],
                            classification=DiffClassification.REAL_MISMATCH,
                            confidence=0.5,
                            agent_classified=True,
                        )
                        for d in ambiguous
                    ]
            elif ambiguous:
                # No agent — default to real_mismatch (conservative)
                for d in ambiguous:
                    agent_classified.append(FieldClassification(
                        field=d["field"],
                        master_value=d["master_value"],
                        company_value=d["company_value"],
                        classification=DiffClassification.REAL_MISMATCH,
                        confidence=0.5,
                        agent_classified=False,
                    ))

            all_classified = det_classified + agent_classified
            real_mismatches = [
                c for c in all_classified
                if c.classification == DiffClassification.REAL_MISMATCH
            ]
            typos = [
                c for c in all_classified
                if c.classification == DiffClassification.LIKELY_TYPO
            ]
            acceptable = [
                c for c in all_classified
                if c.classification == DiffClassification.ACCEPTABLE_VARIATION
            ]

            results.append(ValidationResult(
                enrollment_number=company_record.enrollment_number,
                passed=len(real_mismatches) == 0,
                field_classifications=all_classified,
                real_mismatch_count=len(real_mismatches),
                likely_typo_count=len(typos),
                acceptable_variation_count=len(acceptable),
                needs_human_review=len(real_mismatches) > 0,
            ))

        logger.info(
            f"Validation complete: {sum(1 for r in results if r.passed)} passed, "
            f"{sum(1 for r in results if not r.passed)} failed."
        )
        return results

    def write_validation_report(
        self,
        output_path: str | Path,
        validation_results: list[ValidationResult],
    ) -> None:
        """Write the per-student Validation Report as an Excel file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        rows = []
        for r in validation_results:
            rows.append({
                "enrollment_number": r.enrollment_number,
                "passed": "✅" if r.passed else "❌",
                "real_mismatches": r.real_mismatch_count,
                "likely_typos": r.likely_typo_count,
                "acceptable_variations": r.acceptable_variation_count,
                "missing_fields": ", ".join(r.missing_required_fields),
                "identity_consistent": "✅" if r.identity_consistent else "❌",
                "review_reason": r.review_reason or "",
            })

        df = pd.DataFrame(rows)
        df.to_excel(path, index=False)
        logger.info(f"Written validation report to {path}")

    def write_mismatch_report(
        self,
        output_path: str | Path,
        validation_results: list[ValidationResult],
    ) -> None:
        """Write the focused Mismatch Report (only students with real_mismatches)."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        rows = []
        for r in validation_results:
            for fc in r.field_classifications:
                if fc.classification == DiffClassification.REAL_MISMATCH:
                    rows.append({
                        "enrollment_number": r.enrollment_number,
                        "field": fc.field,
                        "master_db_value": fc.master_value,
                        "company_db_value": fc.company_value,
                        "classification": fc.classification.value,
                        "confidence": round(fc.confidence, 2),
                        "agent_classified": fc.agent_classified,
                    })

        df = pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["enrollment_number", "field", "master_db_value",
                     "company_db_value", "classification", "confidence", "agent_classified"]
        )
        df.to_excel(path, index=False)
        logger.info(f"Written mismatch report to {path} ({len(rows)} mismatches)")

    def get_output_paths(self, run_outputs_dir: str | Path) -> dict[str, str]:
        """Return the standard output file paths for a run's outputs/ directory."""
        base = Path(run_outputs_dir)
        return {
            "populated_db": str(base / OUTPUT_POPULATED_DB),
            "validation_report": str(base / OUTPUT_VALIDATION_REPORT),
            "mismatch_report": str(base / OUTPUT_MISMATCH_REPORT),
        }


# Singleton
report_service = ReportService()
