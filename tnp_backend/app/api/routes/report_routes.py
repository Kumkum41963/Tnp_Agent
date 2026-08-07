"""
Report routes.
GET  /api/v1/reports/{run_id}           — fetch output file paths.
GET  /api/v1/reports/{run_id}/download  — download one of the output files.
POST /api/v1/runs/{run_id}/resume       — resume a paused run after human corrections.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.api.schemas.requests import ResumeRunRequest
from app.api.schemas.responses import ReportResponse, ResumeRunResponse

router = APIRouter(tags=["Reports"])

from app.api.routes.process_routes import _run_states


@router.get("/reports/{run_id}", response_model=ReportResponse)
async def get_reports(run_id: str) -> ReportResponse:
    """Fetch the output file paths for a completed run."""
    state = _run_states.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    return ReportResponse(
        run_id=run_id,
        populated_database_path=state.get("populated_db_path"),
        validation_report_path=state.get("validation_report_path"),
        mismatch_report_path=state.get("mismatch_report_path"),
    )


@router.get("/reports/{run_id}/download")
async def download_report(
    run_id: str,
    report_type: str = "populated_database",
) -> FileResponse:
    """
    Download a generated report file.
    report_type: 'populated_database' | 'validation_report' | 'mismatch_report'
    """
    state = _run_states.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    path_key_map = {
        "populated_database": "populated_db_path",
        "validation_report": "validation_report_path",
        "mismatch_report": "mismatch_report_path",
    }
    if report_type not in path_key_map:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid report_type. Must be one of: {list(path_key_map.keys())}",
        )

    file_path = state.get(path_key_map[report_type])
    if not file_path or not Path(file_path).exists():
        raise HTTPException(
            status_code=404,
            detail=f"'{report_type}' report not yet generated for run '{run_id}'.",
        )

    return FileResponse(
        path=file_path,
        filename=Path(file_path).name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/runs/{run_id}/resume", response_model=ResumeRunResponse)
async def resume_run(run_id: str, request: ResumeRunRequest) -> ResumeRunResponse:
    """
    Resume a pipeline run paused at human_review_gate after coordinator corrections.
    Applies the provided corrections to column mappings and/or identity resolutions,
    then re-runs the pipeline from the merge_form_and_resume_data node.
    """
    from fastapi import BackgroundTasks

    state = _run_states.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    if state.get("status") != "awaiting_human_review":
        raise HTTPException(
            status_code=400,
            detail=f"Run '{run_id}' is not paused for review (status: {state.get('status')}).",
        )

    # Apply column mapping corrections
    from app.models.column_mapping import MappingStatus

    mappings = state.get("column_mappings", [])
    for correction in request.corrections:
        if correction.type == "column_mapping" and correction.company_column:
            for m in mappings:
                if m.company_column == correction.company_column:
                    m.mapped_field = correction.mapped_field
                    m.status = MappingStatus.MAPPED if correction.mapped_field else MappingStatus.MISSING_FIELD
                    m.confidence = 1.0
                    m.reason = "Human review correction applied."

    # Apply identity resolution corrections
    resolved = state.get("resolved_identities", [])
    for correction in request.corrections:
        if correction.type == "identity_resolution" and correction.resume_file:
            for r in resolved:
                if r.resume_file == correction.resume_file:
                    r.resolved_master_record_id = correction.master_record_id
                    r.needs_human_review = False
                    r.resolution_method = "human_correction"
                    r.resolution_confidence = 1.0

    # Update and resume
    state["column_mappings"] = mappings
    state["resolved_identities"] = resolved
    state["status"] = "running"
    _run_states[run_id] = state

    # TODO: Re-invoke graph from merge_form_and_resume_data node
    # For now, return running status and let the coordinator re-trigger validation
    return ResumeRunResponse(run_id=run_id, status="running")
