"""
Shared constants used across the platform.
"""
from __future__ import annotations

# ── Master Database fixed schema ────────────────────────────────────────────
# These column names are the canonical internal field names for the Master DB.
# MASTER_DB_FIELDS: dict[str, str] = {
#     "enrollment_number": "Student enrollment/roll/registration number (unique identifier)",
#     "name": "Student full name",
#     "email": "Student email address",
#     "phone_number": "Student mobile/phone number",
#     "branch": "Academic branch or department (e.g. CSE, ECE, ME)",
#     "cgpa": "Cumulative Grade Point Average",
#     "backlog_count": "Number of active or historical academic backlogs",
#     "gender": "Student gender",
#     "date_of_birth": "Student date of birth",
#     "address": "Student home address",
#     "father_name": "Father's name",
#     "mother_name": "Mother's name",
#     "tenth_percentage": "Class 10 board exam percentage",
#     "twelfth_percentage": "Class 12 board exam percentage",
#     "resume_link": "Link to student resume (Google Drive or similar)",
#     "linkedin_url": "LinkedIn profile URL",
#     "github_url": "GitHub profile URL",
# }

MASTER_DB_FIELDS: dict[str, str] = {
    # Identity
    "enrollment_number": "Student enrollment number (unique identifier)",
    "name": "Student full name",

    # Contact
    "personal_email": "Personal email address",
    "college_email": "College email address",
    "phone_number": "Student mobile number",

    # Academic
    "course": "Degree programme",
    "branch": "Branch/Department",

    "tenth_percentage": "Class 10 percentage",
    "twelfth_percentage": "Class 12 percentage",

    "semester_1_sgpa": "Semester 1 SGPA",
    "semester_2_sgpa": "Semester 2 SGPA",
    "semester_3_sgpa": "Semester 3 SGPA",
    "semester_4_sgpa": "Semester 4 SGPA",
    "semester_5_sgpa": "Semester 5 SGPA",
    "cgpa": "Aggregate CGPA",

    "backlog_status": "Active/Dead backlog status",

    # Personal
    "category": "Reservation category",

    "aadhar_number": "Aadhar number",

    "permanent_address": "Permanent address",
    "temporary_address": "Temporary address",

    # Family
    "father_name": "Father's name",
    "father_occupation": "Father's occupation",
    "father_phone": "Father's mobile number",

    "mother_name": "Mother's name",
    "mother_occupation": "Mother's occupation",
    "mother_phone": "Mother's mobile number",

    # Resume
    "resume_link": "Resume view/download link",

    # Internship (2 months)
    "internship_2m_company": "2-month internship company",
    "internship_2m_role": "2-month internship role",
    "internship_2m_stipend": "2-month internship stipend",

    # Internship (6 months)
    "internship_6m_company": "6-month internship company",
    "internship_6m_role": "6-month internship role",
    "internship_6m_stipend": "6-month internship stipend",

    # PPO
    "ppo_company": "PPO company",
    "ppo_role": "PPO role",
    "ppo_ctc": "PPO package (CTC)",
}


# Fields that MUST always be in any generated Google Form (identity anchors).
FORM_IDENTITY_FIELDS: list[str] = ["enrollment_number", "name"]

# Fields that are personally identifiable and must be treated sensitively.
PII_FIELDS: frozenset[str] = frozenset({
    "email",
    "phone_number",
    "date_of_birth",
    "address",
    "father_name",
    "mother_name",
})

# ── Enrollment number pattern (institution-specific, adjust as needed) ──────
# Example: 21CS045 — 2-digit year + 2-letter branch + 3-digit roll
# ENROLLMENT_NUMBER_PATTERN = r"\b\d{2}[A-Z]{2,4}\d{2,4}\b"
ENROLLMENT_NUMBER_PATTERN = r"\b\d{3}01022023\b"

# ── Agent output field types ─────────────────────────────────────────────────
INFERRED_FIELD_TYPES = frozenset({
    "text",
    "number",
    "date",
    "email",
    "phone",
    "url",
    "file",
})

# ── Validation classification labels ─────────────────────────────────────────
VALIDATION_CLASSIFICATIONS = frozenset({
    "likely_typo",
    "acceptable_variation",
    "real_mismatch",
})

# ── Run status values ────────────────────────────────────────────────────────
RUN_STATUS_RUNNING = "running"
RUN_STATUS_AWAITING_REVIEW = "awaiting_human_review"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"

# ── ChromaDB collection names ────────────────────────────────────────────────
CHROMA_MASTER_FIELDS_COLLECTION = "master_db_fields"

# ── File names for run outputs ───────────────────────────────────────────────
OUTPUT_POPULATED_DB = "populated_company_db.xlsx"
OUTPUT_VALIDATION_REPORT = "validation_report.xlsx"
OUTPUT_MISMATCH_REPORT = "mismatch_report.xlsx"
RUN_STATE_FILE = "run_state.json"
