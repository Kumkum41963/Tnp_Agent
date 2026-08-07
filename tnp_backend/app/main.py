"""
FastAPI application entry point.

Registers all routers, configures startup/shutdown hooks,
and sets up structured logging.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.routes import (
    form_routes,
    master_routes,
    populate_routes,
    process_routes,
    report_routes,
    validate_routes,
)
from app.api.schemas.responses import HealthResponse
from app.config import settings
from app.repositories.vector_repository import vector_repository
from app.utils.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    configure_logging(settings.log_level)
    logger.info("═" * 60)
    logger.info("TNP Automation Platform starting up")
    logger.info(f"  Ollama URL   : {settings.ollama_base_url}")
    logger.info(f"  Ollama Model : {settings.ollama_model}")
    logger.info(f"  Embedding    : {settings.ollama_embedding_model}")
    logger.info(f"  Google APIs  : {'enabled' if settings.google_integration_enabled else 'stubbed'}")
    logger.info(f"  Data dir     : {settings.data_dir}")
    logger.info("═" * 60)

    # Ensure data directories exist
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "master").mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "runs").mkdir(parents=True, exist_ok=True)

    # Pre-warm the ChromaDB vector index for Master DB fields
    # (does not require Ollama — only tries embedding if collection is empty)
    try:
        count = vector_repository.index_master_fields()
        if count == 0:
            logger.warning(
                "ChromaDB master_fields collection is empty. "
                "Embeddings will be generated on first schema mapping run "
                f"(requires Ollama at {settings.ollama_base_url})."
            )
    except Exception as exc:
        logger.warning(
            f"Could not pre-warm vector index (Ollama may not be running yet): {exc}. "
            "The Schema Agent will attempt indexing on first use."
        )

    # It executes shutdown hook to close and clean the code but only after all have ran so ya it pauses when running for above code
    yield

    logger.info("TNP Automation Platform shutting down.")


# ── FastAPI app ──────────────────────────────────────────────────────────────
# instance of FastAPI with metadata, docs, and lifespan hooks
app = FastAPI(
    title="TNP Database Automation Platform",
    description=(
        "AI-powered automation for Training & Placement (TNP) cell workflows: "
        "schema mapping, database population, Google Form generation, "
        "resume identity resolution, and validation reporting."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
# allow all origins for dev; restrcit in prod TODO for prod 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API v1 routers ───────────────────────────────────────────────────────────
# add new routes instance here with a prefix for versioning 
API_PREFIX = "/api/v1"

app.include_router(master_routes.router, prefix=API_PREFIX)
app.include_router(process_routes.router, prefix=f"{API_PREFIX}/process")
app.include_router(populate_routes.router, prefix=API_PREFIX)
app.include_router(form_routes.router, prefix=API_PREFIX)
app.include_router(validate_routes.router, prefix=API_PREFIX)
app.include_router(report_routes.router, prefix=API_PREFIX)

# ── Health check ─────────────────────────────────────────────────────────────
# fxn for monioring and debugging, returns status and some configs of app 
@app.get("/api/v1/health", response_model=HealthResponse, tags=["Health"])
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        ollama_base_url=settings.ollama_base_url,
        google_integration_enabled=settings.google_integration_enabled,
    )


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "name": "TNP Automation Platform",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


# ── Dev entrypoint ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", settings.port))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level=settings.log_level.lower(),
    )


# Pydantic validates and structures data. It ensures that data conforms to the schema you've defined (field names, types, defaults, constraints). It is not a security library for preventing SQL injection or other attacks, although having validated, well-structured input does reduce many classes of bugs and makes it easier to write secure code.