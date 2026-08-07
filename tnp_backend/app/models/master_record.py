"""
Pydantic model for one verified student record from the Master Database.
All fields are optional except the two required identity anchors.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class MasterRecord(BaseModel):
    """One row from the Master Database — the authoritative student record."""

    # ── Required identity fields ──────────────────────────────────────────
    enrollment_number: str = Field(
        description="Unique enrollment / roll / registration number."
    )
    name: str = Field(description="Student full name.")

    # ── Contact ───────────────────────────────────────────────────────────
    email: str | None = None
    phone_number: str | None = None

    # ── Academic ──────────────────────────────────────────────────────────
    branch: str | None = None
    cgpa: float | None = None
    backlog_count: int | None = None

    # ── Personal ──────────────────────────────────────────────────────────
    gender: str | None = None
    date_of_birth: str | None = None
    address: str | None = None
    father_name: str | None = None
    mother_name: str | None = None

    # ── Academic history ──────────────────────────────────────────────────
    tenth_percentage: float | None = None
    twelfth_percentage: float | None = None

    # ── Online profiles ───────────────────────────────────────────────────
    resume_link: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None

    # ── Extra fields not in the fixed schema ──────────────────────────────
    extra: dict[str, str | None] = Field(
        default_factory=dict,
        description="Any additional fields present in the Master DB beyond the known schema.",
    )

    def to_flat_dict(self) -> dict[str, object]:
        """Return all fields as a flat key→value dict (including extras)."""
        base = self.model_dump(exclude={"extra"})
        return {**base, **self.extra}
