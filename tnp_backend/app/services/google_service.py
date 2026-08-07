"""
Google Service — wraps Google Forms v1 and Drive v3 APIs.

Authentication: Google service account JSON file.
Required scopes:
  - https://www.googleapis.com/auth/forms.body                  (create/edit forms)
  - https://www.googleapis.com/auth/forms.responses.readonly    (read responses)
  - https://www.googleapis.com/auth/drive.readonly              (download public Drive files)

Form structure (always):
  Q1  — Enrollment Number  (short text, required — identity anchor)
  Q2  — Student Name       (short text, required — identity anchor)
  Q3  — Resume Drive Link  (short text, required — student pastes their shareable Drive PDF URL)
  Q4… — one question per entry in `missing_fields`

Resume collection model
-----------------------
Students share their resume PDF on Google Drive with "anyone with the link" view
access, then paste that URL into Q3.  We extract the file ID from the URL and
download each PDF via HTTP (works for public share links).  The Drive API is also
tried first in case the service account has direct access.

Supported Drive URL formats:
  https://drive.google.com/file/d/<FILE_ID>/view?usp=sharing
  https://drive.google.com/file/d/<FILE_ID>/view
  https://drive.google.com/open?id=<FILE_ID>
  https://drive.google.com/uc?id=<FILE_ID>
  https://docs.google.com/…/d/<FILE_ID>/…

Set GOOGLE_INTEGRATION_ENABLED=true and GOOGLE_SERVICE_ACCOUNT_FILE=./credentials/…
in .env to activate. Google Forms creation uses OAuth client credentials as well,
so also set GOOGLE_OAUTH_CLIENT_FILE and GOOGLE_OAUTH_TOKEN_FILE.
GOOGLE_DRIVE_FOLDER_ID is only needed when a company's
missing_field has inferred_type="file" (rare edge case).
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

import requests as http_requests
from loguru import logger

from app.config import settings


# ── Constants ────────────────────────────────────────────────────────────────

_SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/forms.responses.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

_SERVICE_ACCOUNT_SCOPES = [
    "https://www.googleapis.com/auth/drive",
]

_OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/drive",
]

# Question titles for the three fixed fields present in every form.
_ENROLLMENT_TITLE = "Enrollment Number"
_NAME_TITLE = "Student Name"
_RESUME_LINK_TITLE = "Resume Drive Link"

# Maps inferred_type to question kind.
_FILE_TYPES = {"file"}
_DATE_TYPES = {"date"}
# All other inferred types → short text

_MAX_FILE_SIZE_BYTES = "10485760"   # 10 MB (used only for file-upload questions in missing_fields)

# Field name key used in response dicts for the resume URL.
_RESUME_LINK_FIELD = "resume_drive_link"


class GoogleServiceError(Exception):
    """Raised on Google API failures."""


# ── URL helpers ───────────────────────────────────────────────────────────────

# All known Drive URL patterns that carry a file ID.
_DRIVE_ID_PATTERNS = [
    re.compile(r"/file/d/([a-zA-Z0-9_-]+)"),          # /file/d/{id}/view
    re.compile(r"[?&]id=([a-zA-Z0-9_-]+)"),            # ?id={id} or &id={id}
    re.compile(r"/d/([a-zA-Z0-9_-]{25,})"),            # generic /d/{id} (≥25 chars)
]


def _extract_drive_file_id(url: str) -> str | None:
    """Return the Drive file ID embedded in any recognised Drive share URL."""
    for pattern in _DRIVE_ID_PATTERNS:
        m = pattern.search(url)
        if m:
            return m.group(1)
    return None


def _to_field_name(title: str) -> str:
    """
    Normalise a question display title to a snake_case dict key.
    e.g. "Enrollment Number" → "enrollment_number"
    """
    s = title.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def _to_display_title(field_name: str) -> str:
    return field_name.replace("_", " ").title()


# ── GoogleService ─────────────────────────────────────────────────────────────

class GoogleService:
    """Wraps Google Forms v1 and Drive v3 APIs."""

    def __init__(self) -> None:
        self._enabled = settings.google_integration_enabled
        self._credentials_file = settings.google_service_account_file
        self._drive_folder_id = settings.google_drive_folder_id

        self._forms_service: Any = None
        self._drive_service: Any = None

        if self._enabled:
            self._init_services()
        else:
            logger.warning(
                "Google integration is DISABLED (GOOGLE_INTEGRATION_ENABLED=false). "
                "GoogleService will return stub data. "
                "Set GOOGLE_INTEGRATION_ENABLED=true and provide a service account JSON "
                "to activate real Google Forms / Drive integration."
            )

    # ── Authentication ────────────────────────────────────────────────────────

    def _init_services(self) -> None:
        """Authenticate with the service account JSON and build API clients."""
        creds_path = Path(self._credentials_file)
        if not creds_path.exists():
            raise GoogleServiceError(
                f"Google service account file not found: {creds_path}. "
                "Set GOOGLE_SERVICE_ACCOUNT_FILE in .env to the correct path."
            )

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            creds = service_account.Credentials.from_service_account_file(
                str(creds_path), scopes=_SERVICE_ACCOUNT_SCOPES
            )
            self._drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
            self._forms_service = None

            logger.info(
                "Google Drive service initialised. "
                "Google Forms client will be initialized lazily via OAuth."
            )
        except ImportError as exc:
            raise GoogleServiceError(
                "Google client libraries not installed. "
                "Run: pip install google-api-python-client google-auth google-auth-oauthlib"
            ) from exc
        except Exception as exc:
            raise GoogleServiceError(f"Failed to initialise Google services: {exc}") from exc

    # def _init_services(self) -> None:
    #     """Initialize only Drive using the Service Account."""
    #     if not settings.google_integration_enabled:
    #         return

    #     creds_path = settings.google_service_account_file

    #     if not creds_path.exists():
    #         raise GoogleServiceError(
    #             f"Google service account credentials not found: {creds_path}"
    #         )

    #     creds = service_account.Credentials.from_service_account_file(
    #         str(creds_path),
    #         scopes=_SERVICE_ACCOUNT_SCOPES,
    #     )

    #     self._drive_service = build(
    #         "drive",
    #         "v3",
    #         credentials=creds,
    #         cache_discovery=False,
    #     )

    #     # Forms service will be initialized lazily via OAuth
    #     self._forms_service = None

    def _get_forms_service(self):
        """Create (or reuse) an OAuth-authenticated Forms service."""

        if self._forms_service is not None:
            return self._forms_service

        token_path = settings.google_oauth_token_file
        client_path = settings.google_oauth_client_file

        from google.oauth2.credentials import Credentials

        creds = None

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(
                str(token_path),
                _OAUTH_SCOPES,
            )

        if not creds or not creds.valid:
            from google.auth.transport.requests import Request
            from google_auth_oauthlib.flow import InstalledAppFlow

            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not client_path.exists():
                    raise GoogleServiceError(
                        f"OAuth client secrets file not found: {client_path}. "
                        "Create Google OAuth credentials and set GOOGLE_OAUTH_CLIENT_FILE."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(client_path),
                    _OAUTH_SCOPES,
                )

                creds = flow.run_local_server(port=0)

            token_path.parent.mkdir(parents=True, exist_ok=True)

            with open(token_path, "w") as token:
                token.write(creds.to_json())

        from googleapiclient.discovery import build

        self._forms_service = build(
            "forms",
            "v1",
            credentials=creds,
            cache_discovery=False,
        )

        return self._forms_service

    # ── Google Forms — create ─────────────────────────────────────────────────

    def create_form(
        self,
        title: str,
        missing_fields: list[dict[str, str]],
    ) -> dict[str, str]:
        """
        Create a Google Form for a company drive.

        Fixed questions (always present):
          1. Enrollment Number  — required text, identity anchor
          2. Student Name       — required text, identity anchor
          3. Resume Drive Link  — required text; students paste their shareable Drive URL

        Dynamic questions (one per missing_field):
          4+. Typed by `inferred_type`: date picker for "date", text for everything else,
              Drive file-upload only when inferred_type=="file" (requires GOOGLE_DRIVE_FOLDER_ID).

        Returns
        -------
        {"form_id": str, "form_url": str}
        """
        if not self._enabled:
            logger.info(f"[STUB] Would create Google Form: '{title}'")
            stub_id = f"STUB_{re.sub(r'[^A-Z0-9]', '_', title.upper())[:24]}"
            return {
                "form_id": stub_id,
                "form_url": f"https://forms.google.com/stub/{stub_id}",
            }

        try:
            # Step 1: Create the bare form
            # form = self._forms_service.forms().create(
            #     body={"info": {"title": title, "documentTitle": title}}
            # ).execute()
            forms_service = self._get_forms_service()
            form = forms_service.forms().create(
            body={
                    "info": {
                    "title": title
                    }
                }
            ).execute()
            form_id: str = form["formId"]
            logger.info(f"Created Google Form: {form_id}")

            # Step 2: Build batchUpdate requests
            requests: list[dict[str, Any]] = [
                self._text_question(_ENROLLMENT_TITLE, index=0, required=True),
                self._text_question(_NAME_TITLE, index=1, required=True),
                # Q3: students paste their own Drive share link (one URL per student)
                self._text_question(
                    _RESUME_LINK_TITLE,
                    index=2,
                    required=True,
                ),
            ]

            for i, field in enumerate(missing_fields):
                field_name: str = field.get("field_name", f"field_{i}")
                inferred_type: str = field.get("inferred_type", "text")
                requests.append(
                    self._question_for_type(
                        title=_to_display_title(field_name),
                        inferred_type=inferred_type,
                        index=3 + i,
                        required=False,
                    )
                )

            forms_service.forms().batchUpdate(
                formId=form_id,
                body={"requests": requests},
            ).execute()

            form_url = f"https://docs.google.com/forms/d/{form_id}/viewform"
            logger.info(
                f"Form '{title}' ready — {len(requests)} questions. URL: {form_url}"
            )
            return {"form_id": form_id, "form_url": form_url}

        except GoogleServiceError:
            raise
        except Exception as exc:
            raise GoogleServiceError(f"Failed to create Google Form: {exc}") from exc

    # ── Google Forms — read responses ─────────────────────────────────────────

    def get_form_responses(self, form_id: str) -> list[dict[str, str]]:
        """
        Fetch all current form responses.

        Returns
        -------
        List of dicts, one per submitted response.  Keys are snake_case field
        names derived from question titles.  The resume share URL appears under
        the key "resume_drive_link".
        Example:
          [
            {
              "enrollment_number": "21CE001",
              "student_name":      "Rahul Shah",
              "resume_drive_link": "https://drive.google.com/file/d/.../view",
              "cgpa":              "8.5",
              ...
            },
            ...
          ]
        """
        if not self._enabled:
            logger.info(f"[STUB] Would fetch responses for form {form_id}")
            return []

        try:
            forms_service = self._get_forms_service()
            question_map = self._get_question_map(form_id)
            # question_map: {questionId: {"field_name": str}}

            raw = forms_service.forms().responses().list(
                formId=form_id
            ).execute()
            raw_responses: list[dict] = raw.get("responses", [])
            logger.info(f"Form {form_id}: {len(raw_responses)} responses.")

            normalized: list[dict[str, str]] = []
            for resp in raw_responses:
                entry: dict[str, str] = {}
                for question_id, answer_data in resp.get("answers", {}).items():
                    meta = question_map.get(question_id)
                    if meta is None:
                        continue
                    text_answers = (
                        answer_data.get("textAnswers", {}).get("answers", [])
                    )
                    if text_answers:
                        entry[meta["field_name"]] = text_answers[0].get("value", "")
                normalized.append(entry)

            return normalized

        except GoogleServiceError:
            raise
        except Exception as exc:
            raise GoogleServiceError(f"Failed to fetch form responses: {exc}") from exc

    # ── Google Drive — download resumes ───────────────────────────────────────

    def download_resume_files(
        self,
        form_id: str,
        download_dir: str,
    ) -> list[str]:
        """
        Download all resume PDFs referenced in form responses.

        How it works
        ------------
        1. Fetches all form responses (includes the "resume_drive_link" field).
        2. For each response that has a Drive URL, extracts the file ID.
        3. Downloads the PDF — tries the Drive API first (authorised), then
           falls back to a direct HTTP download (works for "anyone with the link"
           public shares).
        4. Saves the file as: <download_dir>/<ENROLLMENT_NUMBER>_resume.pdf

        Returns
        -------
        List of absolute local file paths for successfully downloaded PDFs.
        """
        if not self._enabled:
            logger.info(f"[STUB] Would download resumes for form {form_id} → {download_dir}")
            return []

        dest_dir = Path(download_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        try:
            responses = self.get_form_responses(form_id)
            local_paths: list[str] = []

            for i, resp in enumerate(responses):
                drive_url = resp.get(_RESUME_LINK_FIELD, "").strip()
                if not drive_url:
                    logger.debug(f"Response {i}: no resume link — skipping.")
                    continue

                file_id = _extract_drive_file_id(drive_url)
                if not file_id:
                    logger.warning(
                        f"Response {i}: could not parse Drive file ID from URL: {drive_url!r}"
                    )
                    continue

                enrollment = resp.get("enrollment_number", "").strip().upper()
                safe_name = (
                    f"{enrollment}_resume.pdf"
                    if enrollment
                    else f"student_{i}_resume.pdf"
                )
                dest_path = dest_dir / safe_name

                try:
                    self._download_drive_file_by_id(file_id, dest_path)
                    local_paths.append(str(dest_path))
                    logger.info(
                        f"Downloaded resume → {dest_path.name}  "
                        f"(Drive ID: {file_id})"
                    )
                except Exception as exc:
                    label = f"enrollment {enrollment}" if enrollment else f"response {i}"
                    logger.warning(
                        f"Failed to download resume for {label}: {exc}"
                    )

            logger.info(
                f"Resumes: {len(local_paths)} downloaded / {len(responses)} responses."
            )
            return local_paths

        except GoogleServiceError:
            raise
        except Exception as exc:
            raise GoogleServiceError(f"Failed to download resume files: {exc}") from exc

    # ── Internal: Drive download ──────────────────────────────────────────────

    def _download_drive_file_by_id(self, file_id: str, dest_path: Path) -> None:
        """
        Download a Drive file to dest_path.

        Strategy:
          1. Drive API via service account (works when file is shared with the
             service account, or Drive API is enabled on the project).
          2. Direct HTTP download URL — works for "anyone with the link" public shares.
        """
        try:
            self._drive_api_download(file_id, dest_path)
            return
        except Exception as api_err:
            logger.debug(
                f"Drive API download failed for {file_id} ({api_err}); "
                "trying direct HTTP download."
            )

        self._http_download(file_id, dest_path)

    def _drive_api_download(self, file_id: str, dest_path: Path) -> None:
        """Download via Drive API (requires service account access to the file)."""
        from googleapiclient.http import MediaIoBaseDownload

        request = self._drive_service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        dest_path.write_bytes(buf.getvalue())

    @staticmethod
    def _http_download(file_id: str, dest_path: Path) -> None:
        """
        Download a publicly shared Drive file over HTTP.

        Handles Google's large-file virus-scan confirmation cookie automatically.
        """
        session = http_requests.Session()
        base_url = "https://drive.google.com/uc"
        params: dict[str, str] = {"export": "download", "id": file_id}

        response = session.get(base_url, params=params, stream=True, timeout=60)
        response.raise_for_status()

        # Google adds a download_warning cookie for larger files.
        confirm_token: str | None = None
        for key, value in response.cookies.items():
            if key.startswith("download_warning"):
                confirm_token = value
                break

        if confirm_token:
            params["confirm"] = confirm_token
            response = session.get(base_url, params=params, stream=True, timeout=60)
            response.raise_for_status()

        content = b"".join(response.iter_content(chunk_size=32768))
        if not content:
            raise GoogleServiceError(
                f"Downloaded empty content for Drive file {file_id}. "
                "Check that the link sharing is set to 'Anyone with the link'."
            )
        dest_path.write_bytes(content)

    # ── Internal: question map ────────────────────────────────────────────────

    def _get_question_map(self, form_id: str) -> dict[str, dict[str, Any]]:
        """
        Fetch the form and return {questionId: {"field_name": str}}.
        Used when decoding response answers back to named fields.
        """
        forms_service = self._get_forms_service()
        form = forms_service.forms().get(formId=form_id).execute()
        mapping: dict[str, dict[str, Any]] = {}

        for item in form.get("items", []):
            q_item = item.get("questionItem")
            if q_item is None:
                continue
            question = q_item.get("question", {})
            question_id = question.get("questionId")
            if not question_id:
                continue
            title: str = item.get("title", "")
            mapping[question_id] = {"field_name": _to_field_name(title)}

        return mapping

    # ── Question builders ─────────────────────────────────────────────────────

    @staticmethod
    def _text_question(title: str, index: int, required: bool) -> dict[str, Any]:
        return {
            "createItem": {
                "item": {
                    "title": title,
                    "questionItem": {
                        "question": {
                            "required": required,
                            "textQuestion": {"paragraph": False},
                        }
                    },
                },
                "location": {"index": index},
            }
        }

    def _file_upload_question(
        self, title: str, index: int, required: bool
    ) -> dict[str, Any]:
        """
        File-upload question — only used when a company's missing_field has
        inferred_type="file".  Requires GOOGLE_DRIVE_FOLDER_ID.
        """
        if not self._drive_folder_id:
            raise GoogleServiceError(
                f"Question '{title}' has inferred_type='file' but "
                "GOOGLE_DRIVE_FOLDER_ID is not set in .env."
            )
        return {
            "createItem": {
                "item": {
                    "title": title,
                    "questionItem": {
                        "question": {
                            "required": required,
                            "fileUploadQuestion": {
                                "folderId": self._drive_folder_id,
                                "types": ["PDF", "DOCUMENT"],
                                "maxFiles": 1,
                                "maxFileSize": _MAX_FILE_SIZE_BYTES,
                            },
                        }
                    },
                },
                "location": {"index": index},
            }
        }

    @staticmethod
    def _date_question(title: str, index: int, required: bool) -> dict[str, Any]:
        return {
            "createItem": {
                "item": {
                    "title": title,
                    "questionItem": {
                        "question": {
                            "required": required,
                            "dateQuestion": {
                                "includeTime": False,
                                "includeYear": True,
                            },
                        }
                    },
                },
                "location": {"index": index},
            }
        }

    def _question_for_type(
        self,
        title: str,
        inferred_type: str,
        index: int,
        required: bool,
    ) -> dict[str, Any]:
        if inferred_type in _FILE_TYPES:
            return self._file_upload_question(title, index, required)
        if inferred_type in _DATE_TYPES:
            return self._date_question(title, index, required)
        return self._text_question(title, index, required)


# Singleton
google_service = GoogleService()
