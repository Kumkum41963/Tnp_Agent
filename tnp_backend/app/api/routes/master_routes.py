"""
Master Database routes.
POST /api/v1/master/load — load/reload the Master Database from a file path.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.api.schemas.requests import LoadMasterRequest
from app.api.schemas.responses import LoadMasterResponse
from app.repositories.master_repository import master_repository

router = APIRouter(prefix="/master", tags=["Master Database"])


@router.post("/load", response_model=LoadMasterResponse)
async def load_master(request: LoadMasterRequest) -> LoadMasterResponse:
    """
    Load or reload the Master Database from an Excel/CSV file.
    The file must be accessible on the server's filesystem.
    Keep the path format with foward slashes (/) even on Windows. Refrain from using backslashes (\) in the file path.
    """
    try:
        count = master_repository.load(request.file_path)
        return LoadMasterResponse(
            status="loaded",
            record_count=count,
            loaded_at=datetime.utcnow().isoformat() + "Z",
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
