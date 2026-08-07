"""
Validate routes.
POST /api/v1/validate — re-run validation only (after human-review corrections).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas.requests import ValidateRequest
from app.api.schemas.responses import ValidateResponse

router = APIRouter(prefix="/validate", tags=["Validation"])

from app.api.routes.process_routes import _run_states


@router.post("", response_model=ValidateResponse)
async def run_validate(request: ValidateRequest) -> ValidateResponse:
    """
    Re-run the validation stage for an existing run.
    Useful after a coordinator has provided corrections at the human_review_gate.
    """
    state = _run_states.get(request.run_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"Run '{request.run_id}' not found.",
        )

    from app.agents.validation_agent import validation_agent
    from app.graph.nodes import _get_company_repo
    from app.repositories.master_repository import master_repository
    from app.services.report_service import report_service

    if not master_repository.is_loaded():
        raise HTTPException(
            status_code=400,
            detail="Master Database not loaded.",
        )

    repo = _get_company_repo(request.run_id)
    if repo is None:
        raise HTTPException(
            status_code=400,
            detail=f"Company data for run '{request.run_id}' is not in memory. "
                   "Start the full pipeline via POST /api/v1/process first.",
        )

    try:
        validation_results = report_service.build_validation_results(
            master_records=master_repository.list_all(),
            company_records=repo.list_all(),  # type: ignore[attr-defined]
            column_mappings=state.get("column_mappings", []),
            validation_agent=validation_agent,
        )
        # Update run state
        state["validation_results"] = validation_results
        _run_states[request.run_id] = state

        mismatch_count = sum(1 for r in validation_results if r.real_mismatch_count > 0)
        flagged = sum(1 for r in validation_results if r.needs_human_review)

        return ValidateResponse(
            run_id=request.run_id,
            status="completed",
            mismatch_count=mismatch_count,
            flagged_for_review=flagged,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
