"""
Form routes.
GET /api/v1/forms/{run_id} — fetch the generated Google Form link and WhatsApp message.
POST /api/v1/forms/{run_id}/upload — upload a company Excel file to a run's uploads dir.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.schemas.responses import FormStatusResponse
from app.storage.file_storage import file_storage

router = APIRouter(prefix="/forms", tags=["Forms"])

# Shared reference to run states (populated by process_routes)
from app.api.routes.process_routes import _run_states


@router.get("/{run_id}", response_model=FormStatusResponse)
async def get_form_status(run_id: str) -> FormStatusResponse:
    """
    Get the Google Form URL and WhatsApp message generated for a run.
    Available after the pipeline reaches the generate_google_form node.
    """
    state = _run_states.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    return FormStatusResponse(
        run_id=run_id,
        google_form_url=state.get("google_form_url"),
        google_form_id=state.get("google_form_id"),
        whatsapp_message=state.get("whatsapp_message"),
    )


@router.post("/upload", status_code=201)
async def upload_company_file(file: UploadFile = File(...)) -> dict:
    """
    Upload a company Excel/CSV file to a new run directory.
    Returns the run_id and the file path for use in subsequent API calls.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")

    allowed_extensions = {".xlsx", ".xls", ".csv"}
    suffix = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if suffix not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Allowed: {allowed_extensions}",
        )

    run_id = f"r_{uuid.uuid4().hex[:8]}"
    content = await file.read()
    saved_path = file_storage.save_upload(run_id, file.filename, content)

    return {
        "run_id": run_id,
        "file_path": saved_path,
        "message": (
            f"File uploaded successfully. Use run_id='{run_id}' in subsequent API calls."
        ),
    }
