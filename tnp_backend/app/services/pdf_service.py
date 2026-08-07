"""
PDF Service — downloads and parses resume PDFs using PyMuPDF.

Extracts:
- Raw text (concatenation of all pages)
- Lightweight regex pre-extraction for common patterns:
    - Email addresses
    - Phone numbers
    - Enrollment-number-like tokens

The pre-extracted fields are used first by the deterministic identity
hierarchy (FR-10) to avoid invoking the LLM when unnecessary.
"""
from __future__ import annotations

import re
from pathlib import Path

import fitz  # PyMuPDF
from loguru import logger

from app.utils.constants import ENROLLMENT_NUMBER_PATTERN


class PDFServiceError(Exception):
    """Raised on PDF parsing failures."""


# ── Regex patterns ───────────────────────────────────────────────────────────

_EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE
)

_PHONE_PATTERN = re.compile(
    r"""
    (?:
        (?:\+91[-.\s]?)?          # optional India country code
        (?:\(?[6-9]\d{9}\)?)      # 10-digit mobile starting with 6-9
        |
        (?:\+\d{1,3}[-.\s]?)?     # generic country code
        (?:\d{3,5}[-.\s]?\d{3,5}[-.\s]?\d{3,5})  # flexible groups
    )
    """,
    re.VERBOSE,
)

_ENROLLMENT_PATTERN = re.compile(ENROLLMENT_NUMBER_PATTERN)


class PDFService:
    """Parses resume PDFs and extracts structured fields."""

    def parse_resume(self, file_path: str | Path) -> dict[str, object]:
        """
        Parse a single resume PDF.

        Returns
        -------
        dict with keys:
            file_path (str)
            raw_text  (str)   — full extracted text
            email     (str|None)
            phone     (str|None)
            enrollment_number (str|None)
        """
        path = Path(file_path)
        if not path.exists():
            raise PDFServiceError(f"Resume file not found: {path}")

        logger.debug(f"Parsing resume: {path.name}")

        try:
            doc = fitz.open(str(path))
            pages: list[str] = []
            for page in doc:
                pages.append(page.get_text())  # type: ignore[arg-type]
            doc.close()
        except Exception as exc:
            raise PDFServiceError(f"Failed to open/read PDF '{path.name}': {exc}") from exc

        raw_text = "\n".join(pages)

        email = self._extract_email(raw_text)
        phone = self._extract_phone(raw_text)
        enrollment = self._extract_enrollment(raw_text)

        logger.debug(
            f"{path.name}: email={email}, phone={phone}, enrollment={enrollment}"
        )

        return {
            "file_path": str(path),
            "raw_text": raw_text,
            "email": email,
            "phone": phone,
            "enrollment_number": enrollment,
        }

    def extract_contact_page_text(self, raw_text: str, max_chars: int = 3000) -> str:
        """
        Return a bounded excerpt of the resume text for LLM prompting.
        Takes the first max_chars characters (contact info is almost always
        near the top of a resume).
        """
        return raw_text[:max_chars].strip()

    # ── Regex extractors ─────────────────────────────────────────────────────

    @staticmethod
    def _extract_email(text: str) -> str | None:
        match = _EMAIL_PATTERN.search(text)
        return match.group(0).lower() if match else None

    @staticmethod
    def _extract_phone(text: str) -> str | None:
        match = _PHONE_PATTERN.search(text)
        if match:
            # Return only the digits
            raw = match.group(0)
            digits = re.sub(r"\D", "", raw)
            if len(digits) >= 10:
                return digits[-10:]
        return None

    @staticmethod
    def _extract_enrollment(text: str) -> str | None:
        match = _ENROLLMENT_PATTERN.search(text.upper())
        return match.group(0).upper() if match else None


# Singleton
pdf_service = PDFService()
