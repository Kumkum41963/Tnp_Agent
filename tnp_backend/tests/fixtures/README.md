# Test Fixtures

Place test Excel/CSV files here for integration tests.

## Required files

- `master_sample.xlsx` — Sample Master Database with columns:
  `enrollment_number, name, email, phone_number, branch, cgpa, backlog_count`

- `company_sample.xlsx` — Sample company template with arbitrary column names
  (e.g. "Roll No", "Student Name", "Mobile", "LinkedIn URL", "Portfolio Link")

## Creating sample fixtures

You can create these files manually in Excel, or generate them programmatically
with the `openpyxl` or `pandas` libraries for integration testing.

### Suggested company_sample.xlsx columns
| Roll No | Student Name | Mobile | CGPA | Department | LinkedIn | Portfolio |
|---------|-------------|--------|------|------------|----------|-----------|

Where "LinkedIn" and "Portfolio" are intentionally NOT in the Master DB,
so they become missing_fields that trigger Google Form generation.
