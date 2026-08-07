"""
Populate routes.
POST /api/v1/populate — run schema understanding + mapping + population only,
without generating a form. Useful for coordinators to preview mappings first.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.agents.schema_agent import schema_agent
from app.api.schemas.requests import PopulateRequest
from app.api.schemas.responses import ColumnMappingSummary, PopulateResponse
from app.models.column_mapping import MappingStatus
from app.repositories.master_repository import master_repository
from app.services.excel_service import excel_service

router = APIRouter(prefix="/populate", tags=["Population"])


@router.post("", response_model=PopulateResponse)
async def run_populate(request: PopulateRequest) -> PopulateResponse:
    """
    Run schema mapping + population for a company file without starting the full pipeline.
    The run_id must correspond to a directory with an uploaded company file.
    """
    from app.storage.file_storage import file_storage

    if not master_repository.is_loaded():
        raise HTTPException(
            status_code=400,
            detail="Master Database not loaded. Call POST /api/v1/master/load first.",
        )

    # Look for a company file in the run's uploads directory
    uploads_dir = file_storage.get_uploads_dir(request.run_id)
    company_files = list(uploads_dir.glob("*.xlsx")) + list(uploads_dir.glob("*.csv"))
    if not company_files:
        raise HTTPException(
            status_code=404,
            detail=f"No company Excel/CSV file found in uploads for run '{request.run_id}'.",
        )
    company_file = company_files[0]

    try:
        headers, sample_rows = excel_service.parse_company_upload(company_file)
        mappings = schema_agent.run(headers=headers, sample_rows=sample_rows)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    missing_fields = [
        m.company_column for m in mappings if m.status == MappingStatus.MISSING_FIELD
    ]
    mapping_summaries = [
        ColumnMappingSummary(
            company_column=m.company_column,
            mapped_field=m.mapped_field,
            confidence=m.confidence,
            status=m.status.value,
        )
        for m in mappings
    ]

    return PopulateResponse(
        run_id=request.run_id,
        column_mappings=mapping_summaries,
        missing_fields=missing_fields,
    )
