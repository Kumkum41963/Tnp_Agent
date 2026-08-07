"""
LangGraph node functions.

Each node:
- Takes the current PipelineState
- Returns a dict of state keys to update (partial state)
- Never shares state through side channels
- Persists run_state.json after execution
"""
from __future__ import annotations

from loguru import logger

from app.agents.reminder_agent import reminder_agent
from app.agents.resume_extract_identity_agent import resume_extract_identity_agent
from app.agents.schema_agent import schema_agent
from app.agents.validation_agent import validation_agent
from app.graph.state import PipelineState
from app.models.column_mapping import ColumnMapping, MappingStatus
from app.repositories.company_repository import new_company_repository
from app.repositories.master_repository import master_repository
from app.repositories.vector_repository import vector_repository
from app.services.excel_service import excel_service
from app.services.google_service import google_service
from app.services.pdf_service import pdf_service
from app.services.report_service import report_service
from app.services.whatsapp_service import whatsapp_service
from app.storage.file_storage import file_storage
from app.utils.identity_hierarchy import run_deterministic_match

# Per-run company repository (keyed by run_id)
_company_repositories: dict[str, object] = {}


def _get_company_repo(run_id: str):  # type: ignore[return]
    return _company_repositories.get(run_id)


# ── Node implementations ─────────────────────────────────────────────────────


def load_master(state: PipelineState) -> dict:
    """Load the Master Database from disk into memory."""
    run_id = state["run_id"]
    logger.info(f"[{run_id}] Node: load_master")
    try:
        file_path = state.get("master_file_path", "")
        if not file_path:
            return {"errors": [*state.get("errors", []), "master_file_path not set in state"]}
        count = master_repository.load(file_path)
        return {
            "master_records": master_repository.list_all(),
            "current_node": "load_master",
        }
    except Exception as exc:
        logger.exception(f"[{run_id}] load_master failed: {exc}")
        return {
            "status": "failed",
            "errors": [*state.get("errors", []), str(exc)],
        }


def ingest_company_upload(state: PipelineState) -> dict:
    """Parse the company Excel file into headers and sample rows."""
    run_id = state["run_id"]
    logger.info(f"[{run_id}] Node: ingest_company_upload")
    try:
        headers, sample_rows = excel_service.parse_company_upload(
            state["company_file_path"]
        )
        return {
            "company_headers": headers,
            "company_sample_rows": sample_rows,
            "current_node": "ingest_company_upload",
        }
    except Exception as exc:
        logger.exception(f"[{run_id}] ingest_company_upload failed: {exc}")
        return {
            "status": "failed",
            "errors": [*state.get("errors", []), str(exc)],
        }


def run_schema_agent(state: PipelineState) -> dict:
    """Run the Schema Agent to map company columns to Master DB fields."""
    run_id = state["run_id"]
    logger.info(f"[{run_id}] Node: run_schema_agent")
    try:
        headers = state["company_headers"]
        print(headers)
        sample_rows = state.get("company_sample_rows", [])
        print(sample_rows)
        attempts = state.get("schema_mapping_attempts", 0)

        mappings = schema_agent.run(headers=headers, sample_rows=sample_rows)
        low_frac = schema_agent.low_confidence_fraction(mappings)
        from app.config import settings

        needs_review = (
            low_frac > settings.schema_agent_low_confidence_fraction
            and attempts >= settings.schema_agent_max_retries
        )

        return {
            "column_mappings": mappings,
            "schema_mapping_attempts": attempts + 1,
            "schema_needs_review": needs_review,
            "current_node": "run_schema_agent",
        }
    except Exception as exc:
        logger.exception(f"[{run_id}] run_schema_agent failed: {exc}")
        return {
            "status": "failed",
            "errors": [*state.get("errors", []), str(exc)],
        }


def retry_schema_agent(state: PipelineState) -> dict:
    """Re-run the Schema Agent on only the unresolved (low-confidence) columns."""
    run_id = state["run_id"]
    logger.info(f"[{run_id}] Node: retry_schema_agent")
    try:
        unresolved = [
            m.company_column
            for m in state.get("column_mappings", [])
            if m.status == MappingStatus.NEEDS_REVIEW
        ]
        headers = state["company_headers"]
        sample_rows = state.get("company_sample_rows", [])
        new_mappings = schema_agent.run(
            headers=headers,
            sample_rows=sample_rows,
            columns_to_process=unresolved,
        )

        # Merge: keep previously mapped columns, replace reviewed ones
        old_by_col = {m.company_column: m for m in state.get("column_mappings", [])}
        for m in new_mappings:
            if m.status != MappingStatus.SKIPPED:
                old_by_col[m.company_column] = m

        merged = [old_by_col[h] for h in state["company_headers"] if h in old_by_col]
        low_frac = schema_agent.low_confidence_fraction(merged)
        from app.config import settings

        return {
            "column_mappings": merged,
            "schema_needs_review": low_frac > settings.schema_agent_low_confidence_fraction,
            "current_node": "retry_schema_agent",
        }
    except Exception as exc:
        logger.exception(f"[{run_id}] retry_schema_agent failed: {exc}")
        return {
            "status": "failed",
            "errors": [*state.get("errors", []), str(exc)],
        }


def populate_company_db(state: PipelineState) -> dict:
    """Fill company records from Master DB using confident column mappings."""
    run_id = state["run_id"]
    logger.info(f"[{run_id}] Node: populate_company_db")
    try:
        repo = new_company_repository()
        repo.initialize(
            run_id=run_id,
            company_headers=state["company_headers"],
            raw_rows=state.get("company_sample_rows", []),
        )
        repo.populate_from_master(
            master_records=state["master_records"],
            column_mappings=state["column_mappings"],
        )
        _company_repositories[run_id] = repo
        return {"current_node": "populate_company_db"}
    except Exception as exc:
        logger.exception(f"[{run_id}] populate_company_db failed: {exc}")
        return {
            "status": "failed",
            "errors": [*state.get("errors", []), str(exc)],
        }


def detect_missing_fields(state: PipelineState) -> dict:
    """Compute which company-required fields are not in the Master DB."""
    run_id = state["run_id"]
    logger.info(f"[{run_id}] Node: detect_missing_fields")
    missing = [
        m.company_column
        for m in state.get("column_mappings", [])
        if m.status == MappingStatus.MISSING_FIELD
    ]
    logger.info(f"[{run_id}] Missing fields: {missing}")
    return {
        "missing_fields": missing,
        "current_node": "detect_missing_fields",
    }


def generate_google_form(state: PipelineState) -> dict:
    """Create a Google Form with identity fields + missing_field questions."""
    run_id = state["run_id"]
    logger.info(f"[{run_id}] Node: generate_google_form")
    try:
        missing_fields = state.get("missing_fields", [])
        logger.info(f"[{run_id}] Missing fields: {missing_fields}")
        # Build field specs for the form (include inferred type)
        col_types = {
            m.company_column: m.inferred_type
            for m in state.get("column_mappings", [])
        }
        field_specs = [
            {"field_name": f, "inferred_type": col_types.get(f, "text")}
            for f in missing_fields
        ]
        form_result = google_service.create_form(
            title=f"{state.get('company_name', 'Company')} — Additional Details",
            missing_fields=field_specs,
        )
        return {
            "google_form_id": form_result["form_id"],
            "google_form_url": form_result["form_url"],
            "current_node": "generate_google_form",
        }
    except Exception as exc:
        logger.exception(f"[{run_id}] generate_google_form failed: {exc}")
        return {
            "status": "failed",
            "errors": [*state.get("errors", []), str(exc)],
        }


def generate_whatsapp_message(state: PipelineState) -> dict:
    """Draft the WhatsApp distribution message via the Reminder Agent."""
    run_id = state["run_id"]
    logger.info(f"[{run_id}] Node: generate_whatsapp_message")
    draft = reminder_agent.draft_message(
        company_name=state.get("company_name", "the company"),
        deadline=state.get("submission_deadline", "TBD"),
        pending_count=len(state.get("master_records", [])),
    )
    form_url = state.get("google_form_url", "{form_url}")
    message = whatsapp_service.format_message(
        company_name=state.get("company_name", "the company"),
        form_url=form_url,
        deadline=state.get("submission_deadline", "TBD"),
        agent_message=draft,
    )
    return {
        "whatsapp_message": message,
        "current_node": "generate_whatsapp_message",
    }


def await_responses(state: PipelineState) -> dict:
    """
    Pull current Google Form responses.
    This node may loop — the edge logic re-enters if no new responses.
    In the MVP with Google integration stubbed, returns empty immediately.
    """
    run_id = state["run_id"]
    logger.info(f"[{run_id}] Node: await_responses")
    form_id = state.get("google_form_id", "")
    if not form_id:
        return {"form_responses": [], "current_node": "await_responses"}

    responses = google_service.get_form_responses(form_id)
    return {
        "form_responses": responses,
        "current_node": "await_responses",
    }


def parse_resumes(state: PipelineState) -> dict:
    """Parse all downloaded resume PDFs using the PDF Service."""
    run_id = state["run_id"]
    logger.info(f"[{run_id}] Node: parse_resumes")
    resume_files = state.get("resume_files", [])
    parsed: list[dict] = []
    for rf in resume_files:
        try:
            parsed.append(pdf_service.parse_resume(rf))
        except Exception as exc:
            logger.warning(f"Failed to parse resume {rf}: {exc}")
    return {
        "current_node": "parse_resumes",
        # Parsed data is stored temporarily in a state extension key
        "_parsed_resumes": parsed,
    }


def deterministic_identity_match(state: PipelineState) -> dict:
    """Run deterministic identity matching for all parsed resumes."""
    run_id = state["run_id"]
    logger.info(f"[{run_id}] Node: deterministic_identity_match")
    parsed_resumes = state.get("_parsed_resumes", [])
    master_records = state.get("master_records", [])
    form_responses = state.get("form_responses", [])

    # Build form response lookup: enrollment_number → response dict
    form_by_enrollment = {
        r.get("enrollment_number", "").upper(): r for r in form_responses
    }

    resolved: list[ResumeData] = []
    needs_ai: list[dict] = []

    for parsed in parsed_resumes:
        result = run_deterministic_match(
            enrollment=parsed.get("enrollment_number"),
            phone=parsed.get("phone"),
            email=parsed.get("email"),
            all_records=master_records,
        )
        form_declared = form_by_enrollment.get(
            (parsed.get("enrollment_number") or "").upper(), {}
        )
        if result.matched and result.record:
            from app.models.resume_data import ResumeData
            resolved.append(ResumeData(
                resume_file=str(parsed["file_path"]),
                form_declared_enrollment=form_declared.get("enrollment_number"),
                form_declared_name=form_declared.get("name"),
                extracted_enrollment=parsed.get("enrollment_number"),
                extracted_phone=parsed.get("phone"),
                extracted_email=parsed.get("email"),
                resolved_master_record_id=result.record.enrollment_number,
                resolution_method=result.method,
                resolution_confidence=1.0,
                resolution_reason=f"Deterministic match via {result.method}",
            ))
        else:
            needs_ai.append({
                "parsed": parsed,
                "form_declared": form_declared,
                "candidates": result.candidates or [],
            })

    return {
        "resolved_identities": resolved,
        "_needs_ai_resolution": needs_ai,
        "current_node": "deterministic_identity_match",
    }


def run_resume_identity_agent(state: PipelineState) -> dict:
    """Run the AI identity resolution agent for unmatched resumes."""
    run_id = state["run_id"]
    logger.info(f"[{run_id}] Node: run_resume_identity_agent")
    needs_ai = state.get("_needs_ai_resolution", [])
    existing = list(state.get("resolved_identities", []))

    for item in needs_ai:
        result = resume_extract_identity_agent.resolve(
            resume_data_partial=item["parsed"],
            form_declared=item["form_declared"],
            candidates=item["candidates"],
        )
        existing.append(result)

    return {
        "resolved_identities": existing,
        "current_node": "run_resume_identity_agent",
    }


def merge_form_and_resume_data(state: PipelineState) -> dict:
    """Merge form responses + resolved resume data into company records."""
    run_id = state["run_id"]
    logger.info(f"[{run_id}] Node: merge_form_and_resume_data")
    repo = _get_company_repo(run_id)
    if repo is None:
        return {
            "status": "failed",
            "errors": [*state.get("errors", []), "Company repository not found"],
        }
    repo.merge_form_responses(  # type: ignore[attr-defined]
        responses=state.get("form_responses", []),
        missing_fields=state.get("missing_fields", []),
    )
    for resume_data in state.get("resolved_identities", []):
        repo.attach_resume_data(resume_data)  # type: ignore[attr-defined]
    return {"current_node": "merge_form_and_resume_data"}


def run_validation(state: PipelineState) -> dict:
    """Run validation: deterministic diffs + Validation Agent for ambiguous cases."""
    run_id = state["run_id"]
    logger.info(f"[{run_id}] Node: run_validation")
    try:
        repo = _get_company_repo(run_id)
        if repo is None:
            return {
                "status": "failed",
                "errors": [*state.get("errors", []), "Company repository not found"],
            }
        validation_results = report_service.build_validation_results(
            master_records=state.get("master_records", []),
            company_records=repo.list_all(),  # type: ignore[attr-defined]
            column_mappings=state.get("column_mappings", []),
            validation_agent=validation_agent,
        )
        return {
            "validation_results": validation_results,
            "current_node": "run_validation",
        }
    except Exception as exc:
        logger.exception(f"[{run_id}] run_validation failed: {exc}")
        return {
            "status": "failed",
            "errors": [*state.get("errors", []), str(exc)],
        }


def generate_reports(state: PipelineState) -> dict:
    """Write the three final output artifacts."""
    run_id = state["run_id"]
    logger.info(f"[{run_id}] Node: generate_reports")
    try:
        outputs_dir = file_storage.get_outputs_dir(run_id)
        paths = report_service.get_output_paths(outputs_dir)

        # 1. Populated Company DB
        repo = _get_company_repo(run_id)
        if repo is not None:
            rows = repo.to_output_rows(state.get("column_mappings", []))  # type: ignore[attr-defined]
            excel_service.write_populated_database(
                output_path=paths["populated_db"],
                company_headers=repo.company_headers(),  # type: ignore[attr-defined]
                rows=rows,
            )

        # 2. Validation Report
        report_service.write_validation_report(
            output_path=paths["validation_report"],
            validation_results=state.get("validation_results", []),
        )

        # 3. Mismatch Report
        report_service.write_mismatch_report(
            output_path=paths["mismatch_report"],
            validation_results=state.get("validation_results", []),
        )

        return {
            "populated_db_path": paths["populated_db"],
            "validation_report_path": paths["validation_report"],
            "mismatch_report_path": paths["mismatch_report"],
            "status": "completed",
            "current_node": "generate_reports",
        }
    except Exception as exc:
        logger.exception(f"[{run_id}] generate_reports failed: {exc}")
        return {
            "status": "failed",
            "errors": [*state.get("errors", []), str(exc)],
        }


def human_review_gate(state: PipelineState) -> dict:
    """
    Terminal node for runs that require human intervention.
    The run is paused here; it can be resumed via POST /api/v1/runs/{run_id}/resume
    after the coordinator provides corrections.
    """
    run_id = state["run_id"]
    logger.warning(
        f"[{run_id}] Pipeline paused at human_review_gate. "
        "Resume via POST /api/v1/runs/{run_id}/resume after providing corrections."
    )
    return {
        "status": "awaiting_human_review",
        "current_node": "human_review_gate",
    }
