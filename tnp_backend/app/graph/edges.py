"""
LangGraph conditional edge / routing functions.

Each function takes the current PipelineState and returns the name of the
next node to execute (or END).
"""
from __future__ import annotations

from langgraph.graph import END

from app.config import settings
from app.graph.state import PipelineState
from app.models.column_mapping import MappingStatus


def after_run_schema_agent(state: PipelineState) -> str:
    """
    Decide what to do after the Schema Agent runs.

    Options:
    - retry_schema_agent : low-confidence mappings remain AND attempts < max_retries
    - human_review_gate  : low-confidence mappings remain AND attempts >= max_retries
    - populate_company_db: mappings are confident enough to proceed
    """
    if state.get("status") == "failed":
        return END  # type: ignore[return-value]

    mappings = state.get("column_mappings", [])
    attempts = state.get("schema_mapping_attempts", 0)
    low_confidence_count = sum(
        1 for m in mappings if m.status == MappingStatus.NEEDS_REVIEW
    )
    non_skipped = [m for m in mappings if m.status != MappingStatus.SKIPPED]
    low_frac = low_confidence_count / len(non_skipped) if non_skipped else 0.0

    if low_frac > settings.schema_agent_low_confidence_fraction:
        if attempts < settings.schema_agent_max_retries:
            return "retry_schema_agent"
        else:
            return "human_review_gate"

    return "populate_company_db"


def after_detect_missing_fields(state: PipelineState) -> str:
    """
    Route based on whether any fields are missing from the Master DB.

    - generate_google_form : missing_fields is non-empty (need to collect via form)
    - run_validation       : missing_fields is empty (nothing to collect, go straight to validation)
    """
    if state.get("status") == "failed":
        return END  # type: ignore[return-value]

    missing = state.get("missing_fields", [])
    if missing:
        return "generate_google_form"
    return "run_validation"


def after_await_responses(state: PipelineState) -> str:
    """
    Route based on whether form responses are available.

    - parse_resumes   : responses present → proceed with resume processing
    - await_responses : no responses yet → loop back (poll again)

    In the MVP with Google integration stubbed, responses will always be empty
    so this loops to END to avoid infinite looping.
    """
    if state.get("status") == "failed":
        return END  # type: ignore[return-value]

    responses = state.get("form_responses", [])
    if responses:
        return "parse_resumes"

    # For the MVP stub (no real Google Forms), advance to validation
    # so the pipeline can complete without hanging.
    return "run_validation"


def after_deterministic_identity_match(state: PipelineState) -> str:
    """
    Route based on whether all resumes were matched deterministically.

    - merge_form_and_resume_data : no resumes need AI resolution
    - run_resume_identity_agent  : some resumes need AI fallback
    """
    if state.get("status") == "failed":
        return END  # type: ignore[return-value]

    needs_ai = state.get("_needs_ai_resolution", [])
    if needs_ai:
        return "run_resume_identity_agent"
    return "merge_form_and_resume_data"


def after_run_resume_identity_agent(state: PipelineState) -> str:
    """
    Route based on confidence of AI identity resolutions.

    - human_review_gate          : any unresolved / below-threshold identities
    - merge_form_and_resume_data : all resolved (or flagged for review but proceed)
    """
    if state.get("status") == "failed":
        return END  # type: ignore[return-value]

    unresolved = [
        r for r in state.get("resolved_identities", [])
        if r.needs_human_review or r.resolution_failed
    ]
    if unresolved:
        return "human_review_gate"
    return "merge_form_and_resume_data"


def check_status(state: PipelineState) -> str:
    """Generic status check — route to END if failed."""
    if state.get("status") in ("failed", "awaiting_human_review"):
        return END  # type: ignore[return-value]
    return "continue"
