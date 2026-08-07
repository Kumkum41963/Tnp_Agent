"""
File Storage — local filesystem layout for uploads/outputs per run.

Layout:
    data/
    ├── master/                        # Master Database input file (read-only)
    └── runs/
        └── <run_id>/
            ├── uploads/               # Raw company Excel + downloaded resumes
            ├── outputs/               # Populated Company DB, reports
            └── run_state.json         # Serialized pipeline state snapshot
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from loguru import logger

from app.config import settings


class FileStorage:
    """Manages per-run directory layout and run state persistence."""

    def __init__(self) -> None:
        self._base = settings.data_dir
        self._base.mkdir(parents=True, exist_ok=True)
        (self._base / "master").mkdir(parents=True, exist_ok=True)

    # ── Directory helpers ────────────────────────────────────────────────────

    def get_run_dir(self, run_id: str) -> Path:
        return self._base / "runs" / run_id

    def get_uploads_dir(self, run_id: str) -> Path:
        d = self.get_run_dir(run_id) / "uploads"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def get_outputs_dir(self, run_id: str) -> Path:
        d = self.get_run_dir(run_id) / "outputs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def get_state_path(self, run_id: str) -> Path:
        return self.get_run_dir(run_id) / "run_state.json"

    def get_master_dir(self) -> Path:
        return self._base / "master"

    # ── Run initialization ───────────────────────────────────────────────────

    def init_run(self, run_id: str) -> None:
        """Create the directory structure for a new run every pipeline run."""
        self.get_uploads_dir(run_id)
        self.get_outputs_dir(run_id)
        logger.info(f"[{run_id}] Run directory initialized at {self.get_run_dir(run_id)}")

    # ── State persistence ────────────────────────────────────────────────────

    def save_state(self, run_id: str, state: dict) -> None:
        """Persist the current pipeline state to run_state.json."""
        path = self.get_state_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        # State may contain Pydantic models — serialize with a custom handler
        serializable = _make_serializable(state)
        with open(path, "w") as f:
            json.dump({
                "run_id": run_id,
                "saved_at": datetime.utcnow().isoformat(),
                "state": serializable,
            }, f, indent=2, default=str)

    def load_state(self, run_id: str) -> dict | None:
        """Load the last saved pipeline state for a run. Returns None if not found."""
        path = self.get_state_path(run_id)
        if not path.exists():
            return None
        with open(path) as f:
            data = json.load(f)
        return data.get("state")

    # ── File management ──────────────────────────────────────────────────────

    def save_upload(self, run_id: str, filename: str, content: bytes) -> str:
        """Save an uploaded file to the run's uploads/ directory. Returns the path."""
        dest = self.get_uploads_dir(run_id) / filename
        dest.write_bytes(content)
        logger.info(f"[{run_id}] Saved upload: {dest}")
        return str(dest)

    def list_runs(self) -> list[str]:
        """List all run IDs that have a directory."""
        runs_dir = self._base / "runs"
        if not runs_dir.exists():
            return []
        return [d.name for d in runs_dir.iterdir() if d.is_dir()]

    def delete_run(self, run_id: str) -> None:
        """Delete all data for a run (use with caution)."""
        run_dir = self.get_run_dir(run_id)
        if run_dir.exists():
            shutil.rmtree(run_dir)
            logger.info(f"Deleted run directory: {run_dir}")


def _make_serializable(obj: object) -> object:
    """Recursively convert Pydantic models and other non-serializable types."""
    if hasattr(obj, "model_dump"):
        return _make_serializable(obj.model_dump())
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_serializable(i) for i in obj]
    if isinstance(obj, (Path,)):
        return str(obj)
    return obj


# Singleton
file_storage = FileStorage()
