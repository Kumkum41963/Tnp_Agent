"""
Resume Extract Identity Agent — FR-10 (AI fallback).

Only invoked when the deterministic hierarchy (enrollment → phone → email) fails
to produce a unique match. Reasons over unstructured resume text + the form-declared
identity to propose the most likely student match.

Always returns a confidence score. Below threshold → needs_human_review, never
auto-accepted.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.config import settings
from app.models.master_record import MasterRecord
from app.models.resume_data import ResumeData
from app.services.llm_service import LLMServiceError, llm_service
from loguru import logger

# ── LLM Output Schema ────────────────────────────────────────────────────────


class _ResumeIdentityOutput(BaseModel):
    resolved_master_record_id: str | None = Field(
        description="enrollment_number of the matched Master DB record, or null if unresolvable."
    )
    extracted_name: str | None = None
    extracted_phone: str | None = None
    extracted_email: str | None = None
    extracted_enrollment: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


# ── Prompt templates ─────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an identity verification assistant for a college placement cell.
Given resume text and a student's self-declared identity from a form, determine
whether they refer to the same person, and which candidate student in the database
they match.

Be CONSERVATIVE: if you are not confident, return a low confidence score rather
than guessing. It is better to flag a case for human review than to misidentify
a student.

Respond ONLY with a valid JSON object. No prose, no markdown, no code fences.
"""

_USER_PROMPT_TEMPLATE = """\
Form-declared identity:
  Enrollment Number: {form_enrollment}
  Name: {form_name}

Resume text excerpt:
{resume_excerpt}

Candidate students from Master Database:
{candidates_str}

Return a JSON object with this exact schema:
{{
  "resolved_master_record_id": "<enrollment_number or null>",
  "extracted_name": "<name from resume or null>",
  "extracted_phone": "<phone from resume or null>",
  "extracted_email": "<email from resume or null>",
  "extracted_enrollment": "<enrollment number from resume or null>",
  "confidence": <0.0 to 1.0>,
  "reason": "<brief explanation of your decision>"
}}
"""


class ResumeExtractIdentityAgent:
    """
    AI fallback for resume identity resolution when deterministic matching fails.
    """

    def __init__(self) -> None:
        self._threshold = settings.identity_confidence_threshold

    def resolve(
        self,
        resume_data_partial: dict[str, object],
        form_declared: dict[str, str],
        candidates: list[MasterRecord],
    ) -> ResumeData:
        """
        Attempt to resolve a resume to a Master DB record via LLM reasoning.

        Parameters
        ----------
        resume_data_partial : Raw parsed resume data (file_path, raw_text, email, phone, enrollment).
        form_declared       : {"enrollment_number": ..., "name": ...} from the Google Form.
        candidates          : Shortlist of Master DB records that partially matched (may be empty).

        Returns
        -------
        ResumeData with resolved_master_record_id (or None) and a confidence score.
        """
        resume_file = str(resume_data_partial.get("file_path", "unknown"))
        raw_text = str(resume_data_partial.get("raw_text", ""))
        form_enrollment = form_declared.get("enrollment_number", "")
        form_name = form_declared.get("name", "")

        # Truncate resume text for LLM (first 3000 chars → contact info is usually at top)
        resume_excerpt = raw_text[:3000].strip()

        # Build candidates string
        if candidates:
            candidates_str = "\n".join(
                f"  - {r.enrollment_number}: {r.name} | {r.email or ''} | {r.phone_number or ''}"
                for r in candidates[:10]
            )
        else:
            candidates_str = "  (no strong candidates found via deterministic matching)"

        user_prompt = _USER_PROMPT_TEMPLATE.format(
            form_enrollment=form_enrollment,
            form_name=form_name,
            resume_excerpt=resume_excerpt,
            candidates_str=candidates_str,
        )

        try:
            output = llm_service.generate_structured(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                schema=_ResumeIdentityOutput,
                max_retries=1,  # Only 1 retry for this agent (see §7.2)
            )
        except LLMServiceError as exc:
            logger.error(f"ResumeExtractIdentityAgent failed for {resume_file}: {exc}")
            return ResumeData(
                resume_file=resume_file,
                form_declared_enrollment=form_enrollment,
                form_declared_name=form_name,
                resolution_failed=True,
                review_reason=f"LLM resolution failed: {exc}",
            )

        # Confidence gate
        if output.confidence < self._threshold:
            logger.info(
                f"Low confidence ({output.confidence:.2f}) for {resume_file} → "
                f"routing to human review."
            )
            return ResumeData(
                resume_file=resume_file,
                form_declared_enrollment=form_enrollment,
                form_declared_name=form_name,
                extracted_name=output.extracted_name,
                extracted_phone=output.extracted_phone,
                extracted_email=output.extracted_email,
                extracted_enrollment=output.extracted_enrollment,
                resolved_master_record_id=output.resolved_master_record_id,
                resolution_method="ai",
                resolution_confidence=output.confidence,
                resolution_reason=output.reason,
                needs_human_review=True,
                review_reason=(
                    f"AI confidence {output.confidence:.2f} is below threshold "
                    f"{self._threshold:.2f}. Reason: {output.reason}"
                ),
            )

        logger.info(
            f"AI resolved {resume_file} → {output.resolved_master_record_id} "
            f"(confidence={output.confidence:.2f})"
        )
        return ResumeData(
            resume_file=resume_file,
            form_declared_enrollment=form_enrollment,
            form_declared_name=form_name,
            extracted_name=output.extracted_name,
            extracted_phone=output.extracted_phone,
            extracted_email=output.extracted_email,
            extracted_enrollment=output.extracted_enrollment,
            resolved_master_record_id=output.resolved_master_record_id,
            resolution_method="ai",
            resolution_confidence=output.confidence,
            resolution_reason=output.reason,
        )


# Singleton
resume_extract_identity_agent = ResumeExtractIdentityAgent()
