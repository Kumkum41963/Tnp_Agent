"""
Validation Agent (ambiguous diff classification).

The agent is NOT responsible for detecting mismatches (that is deterministic,
done in report_service). It is responsible only for judging ambiguous mismatches
that a human would otherwise have to eyeball.

Batched: all ambiguous diffs for one student are sent in a single prompt.
Conservative default: any diff the agent fails to classify → real_mismatch.
"""
from __future__ import annotations

from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from app.models.validation_result import DiffClassification, FieldClassification
from app.services.llm_service import LLMServiceError, llm_service

# ── LLM Output Schema ────────────────────────────────────────────────────────


class _FieldClassificationOutput(BaseModel):
    field: str
    classification: str = Field(
        description="One of: likely_typo, acceptable_variation, real_mismatch"
    )
    confidence: float = Field(ge=0.0, le=1.0)


class _ValidationAgentOutput(BaseModel):
    classifications: list[_FieldClassificationOutput]


# ── Prompt templates ─────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a data validation assistant for a college placement database.
For each field-level difference between a verified master record and a submitted
company record, classify it as:
  - "likely_typo": minor formatting/case/punctuation difference, same underlying value
  - "acceptable_variation": valid alternative representation (e.g. "CS" vs "Computer Science")
  - "real_mismatch": genuinely different values that must be flagged for correction

IMPORTANT: Prefer flagging over dismissing when uncertain. A false positive
(flagging a typo as a mismatch) is far less harmful than a false negative
(passing a real error silently).

Respond ONLY with a valid JSON object. No prose, no markdown, no code fences.
"""

_USER_PROMPT_TEMPLATE = """\
Student: {student_id}

Field differences to classify:
{diffs_str}

Return a JSON object with this exact schema:
{{
  "classifications": [
    {{
      "field": "<field_name>",
      "classification": "<likely_typo|acceptable_variation|real_mismatch>",
      "confidence": <0.0 to 1.0>
    }},
    ...
  ]
}}
The array MUST have exactly {n_diffs} items, in the SAME order as the input diffs.
"""


class ValidationAgent:
    """
    Classifies ambiguous field-level diffs between Company DB and Master DB records.
    """

    def classify(
        self,
        enrollment_number: str,
        diffs: list[dict[str, str | None]],
    ) -> list[FieldClassification]:
        """
        Classify a batch of diffs for one student.

        Parameters
        ----------
        enrollment_number : Student's enrollment number (for logging/tracing).
        diffs             : List of {"field", "master_value", "company_value"} dicts.

        Returns
        -------
        List of FieldClassification objects (one per input diff, same order).
        """
        if not diffs:
            return []

        diffs_str = "\n".join(
            f"  {i + 1}. Field: {d['field']} | Master: '{d['master_value']}' | "
            f"Company: '{d['company_value']}'"
            for i, d in enumerate(diffs)
        )
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            student_id=enrollment_number,
            diffs_str=diffs_str,
            n_diffs=len(diffs),
        )

        try:
            output = llm_service.generate_structured(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                schema=_ValidationAgentOutput,
                max_retries=2,
            )
        except LLMServiceError as exc:
            logger.error(
                f"ValidationAgent failed for {enrollment_number}: {exc}. "
                "Defaulting all diffs to real_mismatch."
            )
            return self._all_real_mismatch(diffs)

        # Validate output length — must match input
        if len(output.classifications) != len(diffs):
            logger.warning(
                f"ValidationAgent returned {len(output.classifications)} classifications "
                f"for {len(diffs)} diffs ({enrollment_number}). "
                "Padding missing entries with real_mismatch."
            )
            # Pad with real_mismatch for any missing entries
            while len(output.classifications) < len(diffs):
                output.classifications.append(
                    _FieldClassificationOutput(
                        field=diffs[len(output.classifications)]["field"] or "unknown",
                        classification="real_mismatch",
                        confidence=0.5,
                    )
                )

        result: list[FieldClassification] = []
        for i, (diff, cls) in enumerate(zip(diffs, output.classifications)):
            raw_cls = cls.classification.strip().lower()
            if raw_cls not in {c.value for c in DiffClassification}:
                logger.warning(
                    f"Invalid classification '{raw_cls}' for field '{diff['field']}' "
                    f"({enrollment_number}) → defaulting to real_mismatch."
                )
                raw_cls = DiffClassification.REAL_MISMATCH.value

            result.append(FieldClassification(
                field=diff["field"] or cls.field,
                master_value=diff["master_value"],
                company_value=diff["company_value"],
                classification=DiffClassification(raw_cls),
                confidence=cls.confidence,
                agent_classified=True,
            ))
        return result

    @staticmethod
    def _all_real_mismatch(
        diffs: list[dict[str, Any]],
    ) -> list[FieldClassification]:
        return [
            FieldClassification(
                field=d["field"],
                master_value=d["master_value"],
                company_value=d["company_value"],
                classification=DiffClassification.REAL_MISMATCH,
                confidence=0.5,
                agent_classified=True,
            )
            for d in diffs
        ]


# Singleton
validation_agent = ValidationAgent()
