"""
Process routes.
POST /api/v1/process — start a full pipeline run (async, returns run_id immediately).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.api.schemas.requests import ProcessRequest
from app.api.schemas.responses import ProcessResponse
from app.graph.pipeline_graph import pipeline_graph
from app.graph.state import PipelineState
from app.repositories.master_repository import master_repository
from app.storage.file_storage import file_storage

router = APIRouter(prefix="/process", tags=["Pipeline"])

# In-memory run status store (replace with a DB for production)
_run_states: dict[str, dict] = {}


def _get_run_status(run_id: str) -> dict | None:
    return _run_states.get(run_id)


async def _run_pipeline(run_id: str, initial_state: PipelineState) -> None:
    """Background task: invoke the LangGraph pipeline and persist state."""
    try:
        file_storage.init_run(run_id)
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: pipeline_graph.invoke(initial_state),
        )
        _run_states[run_id] = dict(result)
        file_storage.save_state(run_id, dict(result))
    except Exception as exc:
        _run_states[run_id] = {
            "run_id": run_id,
            "status": "failed",
            "errors": [str(exc)],
        }


@router.post("", response_model=ProcessResponse)
async def start_process(
    request: ProcessRequest,
    background_tasks: BackgroundTasks,
) -> ProcessResponse:
    """
    Start a full end-to-end pipeline run for a company upload.
    Returns immediately with a run_id. Use GET /api/v1/reports/{run_id}
    to check completion and retrieve outputs.
    """
    if not master_repository.is_loaded():
        raise HTTPException(
            status_code=400,
            detail="Master Database is not loaded. Call POST /api/v1/master/load first.",
        )

    run_id = f"r_{uuid.uuid4().hex[:8]}"
    _run_states[run_id] = {"run_id": run_id, "status": "running"}

    initial_state: PipelineState = {
        "run_id": run_id,
        "company_name": request.company_name,
        "submission_deadline": request.submission_deadline,
        "master_file_path": "",  # Already loaded in memory
        "master_records": master_repository.list_all(),
        "company_file_path": request.company_file_path,
        "column_mappings": [],
        "schema_mapping_attempts": 0,
        "schema_needs_review": False,
        "missing_fields": [],
        "google_form_id": None,
        "google_form_url": None,
        "whatsapp_message": None,
        "form_responses": [],
        "resume_files": [],
        "resolved_identities": [],
        "identity_resolution_attempts": {},
        "validation_results": [],
        "populated_db_path": None,
        "validation_report_path": None,
        "mismatch_report_path": None,
        "status": "running",
        "current_node": "start",
        "errors": [],
    }

    background_tasks.add_task(_run_pipeline, run_id, initial_state)
    return ProcessResponse(run_id=run_id, status="running")


@router.get("/{run_id}/status")
async def get_run_status(run_id: str) -> dict:
    """Get the current status of a pipeline run."""
    state = _get_run_status(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    return {
        "run_id": run_id,
        "status": state.get("status", "unknown"),
        "current_node": state.get("current_node"),
        "errors": state.get("errors", []),
    }
