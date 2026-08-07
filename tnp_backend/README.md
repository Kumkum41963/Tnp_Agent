# TNP Database Automation Platform

AI-powered automation for Training & Placement (TNP) cell workflows.

## What it does

Given:
- A **Master Database** (Excel/CSV) — verified student records
- A **Company Template** (Excel) — arbitrary company-specific format

The platform automatically:
1. Understands the company's column schema (Schema Agent + embeddings)
2. Maps company columns to Master DB fields semantically
3. Populates matching data from the Master DB
4. Detects fields the company needs that aren't in the Master DB
5. Generates a Google Form to collect only the missing fields
6. Generates a WhatsApp message for student notification
7. Parses uploaded resumes and resolves identities
8. Validates the final data against the Master DB
9. Produces three deliverables: Populated DB, Validation Report, Mismatch Report

## Quick Start

### 1. Copy and configure environment

```bash
cp .env.example .env
# Edit .env — set OLLAMA_BASE_URL to your Ollama server
```

### 2. Set up Ollama

Pull required models on your Ollama server:
```bash
ollama pull llama3.1
ollama pull nomic-embed-text
```

### 3. Start the server

```bash
cd tnp_backend
uvicorn app.main:app --reload --port 8000
```

### 4. Load the Master Database

```bash
curl -X POST http://localhost:8000/api/v1/master/load \
  -H "Content-Type: application/json" \
  -d '{"file_path": "data/master/master_database.xlsx"}'
```

### 5. Upload a company file and run the pipeline

```bash
# Upload company template
curl -X POST http://localhost:8000/api/v1/forms/upload \
  -F "file=@/path/to/company_template.xlsx"
# → Returns: {"run_id": "r_abc123", "file_path": "..."}

# Start the full pipeline
curl -X POST http://localhost:8000/api/v1/process \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "Acme Corp",
    "submission_deadline": "2026-08-15T18:00:00Z",
    "company_file_path": "data/runs/r_abc123/uploads/company_template.xlsx"
  }'
# → Returns: {"run_id": "r_abc123", "status": "running"}

# Check status
curl http://localhost:8000/api/v1/process/r_abc123/status

# Get report paths (after completion)
curl http://localhost:8000/api/v1/reports/r_abc123
```

### 6. View API documentation

Open `http://localhost:8000/docs` for the interactive Swagger UI.

## API Reference

All endpoints are prefixed `/api/v1`. See `/docs` for full OpenAPI spec.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/master/load` | Load/reload the Master Database |
| POST | `/forms/upload` | Upload a company Excel file |
| POST | `/process` | Start a full pipeline run |
| GET | `/process/{run_id}/status` | Check run status |
| POST | `/populate` | Schema mapping + population preview only |
| GET | `/forms/{run_id}` | Get generated form URL + WhatsApp message |
| POST | `/validate` | Re-run validation after corrections |
| GET | `/reports/{run_id}` | Get output file paths |
| GET | `/reports/{run_id}/download` | Download a report file |
| POST | `/runs/{run_id}/resume` | Resume a paused run after human review |
| GET | `/health` | Health check |

## Architecture

See `ARCHITECTURE.md` (the uploaded architecture document) for the full design.

Key components:
- **FastAPI** — async API layer
- **LangGraph** — stateful multi-agent workflow orchestration
- **Ollama** — local/private LLM inference (your server)
- **ChromaDB** — local vector store for semantic column mapping
- **Pandas + OpenPyXL** — Excel I/O
- **PyMuPDF** — Resume PDF parsing
- **Loguru** — Structured logging

## Google Integration (optional)

Google Forms and Drive integration is stubbed by default.
To enable real Google integration:
1. Set `GOOGLE_INTEGRATION_ENABLED=true` in `.env`
2. Add your service account JSON at `GOOGLE_SERVICE_ACCOUNT_FILE` for Drive access
3. Add OAuth client credentials at `GOOGLE_OAUTH_CLIENT_FILE` for Forms API authorization
4. Install: `pip install google-api-python-client google-auth google-auth-oauthlib`

## Running Tests

```bash
cd tnp_backend
pytest tests/ -v
```


## Overall Flow 
```
Start
  │
  ▼
Load Documents
  │
  ▼
Resume Identity Agent
  │
  ▼
Resume Parsing Agent
  │
  ▼
Validation Agent
  │
  ▼
Store Structured Profile
  │
  ▼
Wait for New Company JD
  │
  ▼
JD Parsing Agent
  │
  ▼
Eligibility Agent
  │
  ▼
AI Matching Agent
  │
  ▼
Ranking Agent
  │
  ▼
Human Review (Optional)
  │
  ▼
Generate Reports
  │
  ▼
Send Emails
  │
  ▼
End
```

# TNP Database Automation Platform

AI-powered automation for Training & Placement (TNP) cell workflows. Given a Master Student Database and an arbitrary company Excel template, the system automatically maps columns, fills data from the master records, generates a Google Form for missing fields, parses student resumes, resolves identities, validates data, and produces three deliverable files: **Populated Company Database**, **Validation Report**, and **Mismatch Report**.

---

## Quick Start

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env: set OLLAMA_BASE_URL to your server

# 2. Start the server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 3. Open interactive API docs
# http://localhost:8000/docs

# 4. Run unit tests
pytest tests/ -v
```

---

## How a Run Works (End-to-End Flow)

```
Coordinator                     API                      LangGraph Pipeline
──────────────────────────────────────────────────────────────────────────────

1. Load Master DB    ──►  POST /master/load
                                │
                                ▼ master_repository.load()

2. Upload company    ──►  POST /forms/upload
   Excel file                   │
                                ▼ file_storage.save_upload()
                                  returns run_id

3. Start pipeline    ──►  POST /process
                                │
                                ▼ background task → LangGraph invoked
                                │
                          ┌─────▼─────────────────────────────────────────┐
                          │  load_master                                   │
                          │      └─► Load MasterRecords into state         │
                          │  ingest_company_upload                         │
                          │      └─► ExcelService reads headers + 5 rows   │
                          │  run_schema_agent                              │
                          │      └─► EmbeddingService: embed each column   │
                          │      └─► VectorRepository: top-k candidates    │
                          │      └─► LLMService: pick best match → ColumnMapping │
                          │      ┌─[too many low-confidence?]              │
                          │      ├─► retry_schema_agent (max 2 retries)    │
                          │      └─► human_review_gate (if retries exhausted) │
                          │  populate_company_db                           │
                          │      └─► CompanyRepository.populate_from_master() │
                          │  detect_missing_fields                         │
                          │      ┌─[missing fields exist?]                 │
                          │      ├─► generate_google_form                  │
                          │      │       └─► GoogleService.create_form()   │
                          │      │   generate_whatsapp_message             │
                          │      │       └─► ReminderAgent.draft_message() │
                          │      │   await_responses                       │
                          │      │       └─► GoogleService.get_form_responses() │
                          │      │       ┌─[responses received?]           │
                          │      │       ├─► parse_resumes                 │
                          │      │       │       └─► PDFService.parse_resume() │
                          │      │       │   deterministic_identity_match  │
                          │      │       │       └─► identity_hierarchy chain │
                          │      │       │       ┌─[unresolved resumes?]   │
                          │      │       │       ├─► run_resume_identity_agent │
                          │      │       │       │   └─► LLMService → confidence gate │
                          │      │       │       └─► merge_form_and_resume_data │
                          │      │       └─[no responses / stub] ──────────┤
                          │      └─[no missing fields] ─────────────────── ┤
                          │  run_validation                                 │
                          │      └─► ReportService.build_validation_results() │
                          │      └─► ValidationAgent.classify() for diffs  │
                          │  generate_reports                               │
                          │      └─► Write 3 Excel output files             │
                          └─────────────────────────────────────────────────┘

4. Check status      ──►  GET /process/{run_id}/status
5. Get form link     ──►  GET /forms/{run_id}
6. Download outputs  ──►  GET /reports/{run_id}/download?report_type=populated_database
```

---

## Configuration

Copy `.env.example` → `.env` and set these variables:

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL of your Ollama server |
| `OLLAMA_MODEL` | `llama3.1` | Chat model for agents |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model for schema mapping |
| `LLM_TEMPERATURE` | `0.1` | Temperature for schema/validation agents |
| `LLM_REMINDER_TEMPERATURE` | `0.3` | Higher temperature for message drafting |
| `COLUMN_MAPPING_CONFIDENCE_THRESHOLD` | `0.7` | Minimum confidence to auto-accept a mapping |
| `IDENTITY_CONFIDENCE_THRESHOLD` | `0.75` | Minimum AI confidence to auto-accept resume identity |
| `SCHEMA_AGENT_MAX_RETRIES` | `2` | How many times to retry poor schema mappings |
| `GOOGLE_INTEGRATION_ENABLED` | `false` | Set `true` to use real Google Forms/Drive |
| `DATA_DIR` | `./data` | Root directory for all run data |
| `LOG_LEVEL` | `INFO` | DEBUG / INFO / WARNING / ERROR |

---

## API Reference

All endpoints are prefixed with `/api/v1`. Interactive docs at `/docs`.

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check — confirms server + config |
| POST | `/master/load` | Load Master Database from an Excel/CSV path |
| POST | `/forms/upload` | Upload company Excel; returns `run_id` |
| POST | `/process` | Start full async pipeline; returns `run_id` immediately |
| GET | `/process/{run_id}/status` | Poll pipeline progress |
| POST | `/populate` | Schema mapping + population preview (no form) |
| GET | `/forms/{run_id}` | Get generated Google Form URL + WhatsApp message |
| POST | `/validate` | Re-run validation (after human corrections) |
| GET | `/reports/{run_id}` | Get output file paths for a completed run |
| GET | `/reports/{run_id}/download` | Download one of the three output files |
| POST | `/runs/{run_id}/resume` | Resume a run paused at human_review_gate |

---

## Full Project Structure

```
tnp_backend/
│
├── .env.example               ← All env vars documented
├── .gitignore
├── pyproject.toml             ← Python project + dependency declarations
├── README.md                  ← This file
│
├── data/                      ← Runtime data (gitignored)
│   ├── master/                ← Place your master_database.xlsx here
│   └── runs/
│       └── <run_id>/
│           ├── uploads/       ← Uploaded company Excel + downloaded resumes
│           ├── outputs/       ← Generated Excel outputs
│           └── run_state.json ← Serialized pipeline snapshot
│
├── tests/
│   ├── fixtures/README.md     ← Instructions for creating test fixtures
│   ├── unit/
│   │   ├── test_identity_hierarchy.py
│   │   └── test_report_service.py
│
└── app/
    ├── main.py                ← FastAPI app + startup hooks  [ENTRY POINT]
    ├── config.py              ← Pydantic Settings singleton
    │
    ├── utils/
    │   ├── constants.py       ← Master DB field catalogue, regex patterns, status codes
    │   ├── logging.py         ← Loguru setup + run-scoped logger
    │   └── identity_hierarchy.py  ← Deterministic enrollment→phone→email matching
    │
    ├── models/
    │   ├── master_record.py   ← MasterRecord (authoritative student row)
    │   ├── company_record.py  ← CompanyRecord + RecordStatus enum (in-progress row)
    │   ├── column_mapping.py  ← ColumnMapping + MappingStatus enum
    │   ├── resume_data.py     ← ResumeData (parsed PDF + identity resolution)
    │   ├── validation_result.py ← ValidationResult, FieldClassification, DiffClassification
    │   └── run.py             ← Run + RunStatus (run lifecycle metadata)
    │
    ├── services/
    │   ├── llm_service.py         ← ChatOllama wrapper: generate_text, generate_structured
    │   ├── embedding_service.py   ← OllamaEmbeddings wrapper: embed, embed_query
    │   ├── vector_service.py      ← ChromaDB PersistentClient: upsert, query_similar
    │   ├── excel_service.py       ← Pandas+OpenPyXL: load master, parse upload, write output
    │   ├── pdf_service.py         ← PyMuPDF: extract text + regex email/phone/enrollment
    │   ├── google_service.py      ← STUB: create_form, get_form_responses, download_resumes
    │   ├── whatsapp_service.py    ← Format + (stub) send WhatsApp messages
    │   └── report_service.py      ← Build ValidationResults, write 3 Excel reports
    │
    ├── repositories/
    │   ├── master_repository.py      ← In-memory Master DB with enrollment/phone/email indices
    │   ├── company_repository.py     ← Per-run Company DB: populate, merge, attach, export
    │   ├── vector_repository.py      ← ChromaDB collection lifecycle for Master DB fields
    │   └── collection_repository.py  ← Read + normalize Google Form responses
    │
    ├── agents/
    │   ├── schema_agent.py                    ← Map company columns → Master DB fields
    │   ├── resume_extract_identity_agent.py   ← AI fallback for resume identity resolution
    │   ├── validation_agent.py                ← Classify ambiguous field diffs
    │   └── reminder_agent.py                  ← Draft WhatsApp reminder messages
    │
    ├── graph/
    │   ├── state.py           ← PipelineState TypedDict (all fields threaded through nodes)
    │   ├── nodes.py           ← 16 LangGraph node functions (one per pipeline step)
    │   ├── edges.py           ← 5 conditional routing functions (branch logic)
    │   └── pipeline_graph.py  ← Assembles + compiles the StateGraph; exports singleton
    │
    ├── storage/
    │   ├── file_storage.py    ← Per-run directory layout, state persistence to JSON
    │   └── chroma_store/      ← ChromaDB on-disk persistence (auto-created)
    │
    └── api/
        ├── schemas/
        │   ├── requests.py    ← Pydantic request models for every endpoint
        │   └── responses.py   ← Pydantic response models for every endpoint
        └── routes/
            ├── master_routes.py    ← POST /master/load
            ├── process_routes.py   ← POST /process, GET /process/{run_id}/status
            ├── populate_routes.py  ← POST /populate
            ├── form_routes.py      ← GET /forms/{run_id}, POST /forms/upload
            ├── validate_routes.py  ← POST /validate
            └── report_routes.py    ← GET /reports/{run_id}, /download, POST /runs/{id}/resume
```

---

## File-by-File Reference

Each section follows the actual execution order from server startup to pipeline completion.

---

### Startup Chain

#### `app/main.py` — Entry Point

The very first file Python executes. Does four things in order:

1. **Imports** `config.py`, all six routers, and `vector_repository`.
2. **`lifespan()` hook** (runs before the server accepts requests):
   - Calls `configure_logging()` to set up Loguru.
   - Creates `data/master/`, `data/runs/` directories if missing.
   - Calls `vector_repository.index_master_fields()` to pre-warm ChromaDB with the Master DB field catalogue. If Ollama is not running yet, it logs a warning and continues — the Schema Agent will retry on first use.
3. **Creates the FastAPI `app`** with CORS middleware (allow all origins).
4. **Registers all routers** under the `/api/v1` prefix, plus the `/health` and `/` endpoints.

#### `app/config.py` — Settings Singleton

Loaded by `main.py` at import time. Reads all environment variables from `.env` using Pydantic Settings. Exposes a single `settings` object imported everywhere. Validates types and ranges (e.g. `llm_temperature` must be 0.0–2.0). Every other file does `from app.config import settings` — nothing is hardcoded.

---

### Utilities (loaded at import time, no side effects)

#### `app/utils/constants.py`

Defines pure data that nothing else computes:
- `MASTER_DB_FIELDS` — the 17 canonical field names + human descriptions. This dict is the single source of truth for what the Master Database can contain. The Schema Agent maps company columns to these names; the embedding index is built from these descriptions.
- `ENROLLMENT_NUMBER_PATTERN` — regex for institution-specific roll numbers (e.g. `21CS045`). Used by the PDF Service and identity hierarchy. **Adjust this if your institution uses a different format.**
- `FORM_IDENTITY_FIELDS`, `PII_FIELDS`, `VALIDATION_CLASSIFICATIONS` — used by agents and reports.
- `OUTPUT_POPULATED_DB`, `OUTPUT_VALIDATION_REPORT`, `OUTPUT_MISMATCH_REPORT` — standardized output filenames.

#### `app/utils/logging.py`

Two functions:
- `configure_logging(level)` — removes Loguru's default handler, adds a stderr sink with colour formatting. Called once by `main.py` lifespan.
- `get_run_logger(run_id)` — returns a logger pre-bound with `run_id` context so every log line from a pipeline run is traceable.

#### `app/utils/identity_hierarchy.py`

Pure functions implementing the three-step deterministic student matching algorithm (FR-10). Called by `nodes.py` inside the `deterministic_identity_match` node.

**Algorithm:**
1. Normalize and look up `enrollment_number` in all Master records. If exactly one match → return it. If >1 → fall through.
2. Normalize and look up `phone_number` (last 10 digits). If exactly one match → return it.
3. Normalize and look up `email` (lowercase + strip). If exactly one match → return it.
4. If all three fail → return `matched=False` to signal the AI agent must be invoked.

Returns a `DeterministicMatchResult` dataclass. Also exports `normalize_phone`, `normalize_email`, `normalize_enrollment` — used by `master_repository.py` to build indices.

---

### Domain Models

All models are Pydantic v2 `BaseModel`. They carry data through the system; they contain no business logic beyond field validation.

#### `app/models/master_record.py` — `MasterRecord`

One row from the Master Database. Two fields are required (`enrollment_number`, `name`). All others (email, phone, branch, CGPA, etc.) are optional. An `extra` dict catches any additional columns in the actual file beyond the known 17. `to_flat_dict()` merges known + extra fields into one dict for comparison and output.

#### `app/models/company_record.py` — `CompanyRecord` + `RecordStatus`

One row in the Company Database for a specific run. Starts as `PENDING`, progresses through `POPULATED` → `COMPLETE`. Contains:
- `data` — company column headers mapped to values from the Master DB.
- `missing_field_values` — values filled in via Google Form.
- Resume resolution metadata (file, matched enrollment, confidence, method).
- `RecordStatus` enum: `pending`, `populated`, `complete`, `incomplete`, `needs_review`.

#### `app/models/column_mapping.py` — `ColumnMapping` + `MappingStatus`

One mapping produced by the Schema Agent per company column. Key fields:
- `company_column` — original header from the company's file.
- `mapped_field` — canonical Master DB field name it maps to (or `None`).
- `confidence` — 0.0–1.0 score from the LLM.
- `status` — `mapped` / `missing_field` / `needs_review` / `skipped`.
- `review_candidates` — top-k shortlist shown to human reviewers.

#### `app/models/resume_data.py` — `ResumeData`

Output of resume processing. Contains extracted contact fields (email, phone, enrollment from PDF text), plus identity resolution metadata (which Master record it resolved to, what method was used, confidence score, and flags for `needs_human_review` or `resolution_failed`).

#### `app/models/validation_result.py` — `ValidationResult`, `FieldClassification`, `DiffClassification`

Per-student validation outcome. `FieldClassification` represents one field-level diff:
- `classification` — `likely_typo` / `acceptable_variation` / `real_mismatch`.
- `agent_classified` — `True` if the LLM decided; `False` if deterministic code decided.

`ValidationResult` aggregates all field classifications for one student plus pass/fail, counts, and review flags.

#### `app/models/run.py` — `Run` + `RunStatus`

Serializable run lifecycle metadata (company name, deadline, status, timestamps, output paths, summary statistics). Serialized to `run_state.json` after every pipeline node for resumability.

---

### Services

Services are stateless utilities. Each is a singleton imported where needed. They know nothing about the pipeline or LangGraph — they just do one job well.

#### `app/services/llm_service.py` — `LLMService`

The single point of contact with Ollama. Two public methods:

- `generate_text(system, user)` — plain string output. Used by the Reminder Agent for WhatsApp message drafts.
- `generate_structured(system, user, schema, max_retries)` — calls the LLM, strips markdown fences, parses JSON, validates against a Pydantic schema. If parsing or validation fails, it appends a correction turn to the conversation and retries up to `max_retries` times. Raises `LLMServiceError` after all retries. Used by the Schema Agent, Resume Identity Agent, and Validation Agent.

Internally maintains two `ChatOllama` instances — one at `LLM_TEMPERATURE` (for data decisions) and one at `LLM_REMINDER_TEMPERATURE` (for message drafting).

#### `app/services/embedding_service.py` — `EmbeddingService`

Thin wrapper around `OllamaEmbeddings`. Lazy-initializes the client on first use. Two methods: `embed(texts)` for bulk documents, `embed_query(text)` for single queries. Raises `EmbeddingServiceError` with a human-readable message if Ollama is unreachable or the model is not pulled.

#### `app/services/vector_service.py` — `VectorService`

Owns the ChromaDB `PersistentClient` at `app/storage/chroma_store/`. Provides `upsert(collection, ids, texts, metadatas)` and `query_similar(collection, query_text, top_k)`. Uses cosine similarity (`hnsw:space=cosine`). Distances are 0 (identical) to 1 (orthogonal). Completely unaware of what the data means — just stores and retrieves vectors.

#### `app/services/excel_service.py` — `ExcelService`

All Excel/CSV I/O. Three methods:

- `load_master_database(path)` — reads the Master DB with Pandas, normalizes column names (lowercase + snake_case), applies column aliases (e.g. `roll_no` → `enrollment_number`), validates required columns, returns `list[MasterRecord]`.
- `parse_company_upload(path)` — reads the company file, preserves original header capitalisation exactly (critical — the Schema Agent needs them as-is), returns `(headers, sample_rows[:5])`.
- `write_populated_database(path, headers, rows)` — writes output with OpenPyXL. Applies bold white text + dark green fill to the header row.

#### `app/services/pdf_service.py` — `PDFService`

Uses PyMuPDF (`fitz`) to open PDF files and extract text page by page. Then runs three regex extractors:
- Email: standard email pattern.
- Phone: India-aware pattern (country code, 10-digit mobile) with fallback to generic groups. Returns last 10 digits only.
- Enrollment number: uses `ENROLLMENT_NUMBER_PATTERN` from `constants.py`.

Returns a dict with `file_path`, `raw_text`, `email`, `phone`, `enrollment_number`. The `raw_text` is passed to the AI agent if deterministic matching fails.

#### `app/services/google_service.py` — `GoogleService` *(stub)*

Defines the full interface for Google Forms, Sheets, and Drive. When `GOOGLE_INTEGRATION_ENABLED=false` (the default), all methods return safe stubs:
- `create_form()` → returns a fake form ID and URL.
- `get_form_responses()` → returns `[]`.
- `download_resume_files()` → returns `[]`.

The real implementation is documented in `TODO` comments inside each method. To enable: set `GOOGLE_INTEGRATION_ENABLED=true`, provide a service account JSON, and install `pip install tnp-automation-platform[google]`.

#### `app/services/whatsapp_service.py` — `WhatsAppService`

Formats the final WhatsApp message string. In MVP, sending is a no-op (the `StubSender` just logs). Uses the `WhatsAppSender` Protocol so a real Twilio/WhatsApp Business backend can be plugged in later without changing calling code. `format_message()` substitutes the actual form URL into the Reminder Agent's draft or falls back to a static template if the agent provided nothing.

#### `app/services/report_service.py` — `ReportService`

The most complex service. Three responsibilities:

1. **`build_validation_results(master, company, mappings, agent)`** — for every company record:
   - Looks up the matching Master record by enrollment number.
   - Calls `compute_diffs()` to find field-level differences (only for `MAPPED` columns).
   - Calls `classify_diffs_deterministically()` to resolve obvious cases without LLM:
     - One side is empty → `real_mismatch`.
     - Alphanumeric-stripped values are equal → `acceptable_variation`.
     - Anything else → passed to the agent.
   - Calls `ValidationAgent.classify()` for remaining ambiguous diffs.
   - Assembles `ValidationResult` per student.

2. **`write_validation_report(path, results)`** — one row per student with pass/fail indicator, counts, and review reason.

3. **`write_mismatch_report(path, results)`** — one row per `real_mismatch` field across all students, with Master value, Company value, classification, and confidence.

---

### Repositories

Repositories manage data access patterns. They sit between services (which do I/O) and nodes (which orchestrate).

#### `app/repositories/master_repository.py` — `MasterRepository`

Singleton. Wraps `excel_service.load_master_database()` and builds three in-memory hash-map indices after loading:
- `_by_enrollment` — `{normalized_enrollment → MasterRecord}` (unique).
- `_by_phone` — `{normalized_phone → list[MasterRecord]}` (may have duplicates).
- `_by_email` — `{normalized_email → list[MasterRecord]}` (may have duplicates).

`get_by_enrollment()`, `get_by_phone()`, `get_by_email()` enable O(1) lookups for the identity hierarchy. Raises `MasterRepositoryError` if accessed before `load()` is called.

#### `app/repositories/company_repository.py` — `CompanyRepository`

Created fresh per run (via `new_company_repository()` factory — not a singleton). Holds the in-progress Company Database for one run. Three enrichment phases:

1. `initialize(run_id, headers, raw_rows)` — stores raw rows by index.
2. `populate_from_master(master_records, column_mappings)` — creates one `CompanyRecord` per student, filling each company column from the corresponding Master DB field via the mappings.
3. `merge_form_responses(responses, missing_fields)` — fills in `missing_field_values` from Google Form responses, keyed by enrollment number.
4. `attach_resume_data(resume_data)` — links a resolved resume identity to the matching record.

`to_output_rows(mappings)` exports all records as plain dicts ready for the Excel Service to write.

#### `app/repositories/vector_repository.py` — `VectorRepository`

Singleton. Manages the `master_db_fields` ChromaDB collection lifecycle. `index_master_fields()` upserts all 17 `MASTER_DB_FIELDS` entries (field name + description as document text) into ChromaDB using the Embedding Service. Safe to call multiple times — skips re-indexing if the count already matches. `query_similar_fields(text, top_k)` delegates to `vector_service.query_similar()`.

#### `app/repositories/collection_repository.py` — `CollectionRepository`

Per-run (not singleton). Wraps `google_service.get_form_responses()` and normalizes the raw Sheet rows: maps common header variations (`enroll_no`, `reg_no`, `student_name`, etc.) to canonical field names. `get_pending_enrollments(all_enrollments)` returns students who haven't responded yet.

---

### AI Agents

Agents are where the LLM is actually invoked. Each uses `llm_service.generate_structured()` with a Pydantic output schema. All are singletons.

#### `app/agents/schema_agent.py` — `SchemaAgent`

**Purpose:** Map each company column header to a canonical Master DB field name.

**Two-stage process per column:**
1. **Embedding search** — calls `vector_repository.query_similar_fields(column_name + sample_values, top_k=5)` to retrieve the 5 most semantically similar Master DB fields.
2. **LLM reasoning** — sends the column name, sample cell values, and the 5 candidate fields to the LLM. The LLM returns a `_ColumnMappingOutput` (matched field, inferred type, confidence, reason). This prevents the LLM from hallucinating field names not in the Master DB.

**Result:** `MAPPED` if `confidence >= COLUMN_MAPPING_CONFIDENCE_THRESHOLD`, `NEEDS_REVIEW` if below, `MISSING_FIELD` if LLM returns `null`.

`low_confidence_fraction(mappings)` — returns the fraction of non-skipped mappings that are `NEEDS_REVIEW`. Used by `nodes.py` to decide whether to retry or escalate.

#### `app/agents/resume_extract_identity_agent.py` — `ResumeExtractIdentityAgent`

**Purpose:** AI fallback when the deterministic enrollment→phone→email chain fails.

**Input:** partial resume data (raw text), form-declared identity (enrollment + name from form response), and a shortlist of candidate Master records.

**Process:** Sends the first 3000 chars of resume text + form-declared identity + up to 10 candidates to the LLM. The LLM returns an enrollment number + confidence.

**Confidence gate:** If `confidence < IDENTITY_CONFIDENCE_THRESHOLD` → sets `needs_human_review=True` instead of auto-accepting. Conservative by design: false positives (flagging a correct match) are far less harmful than false negatives (auto-accepting a wrong identity).

#### `app/agents/validation_agent.py` — `ValidationAgent`

**Purpose:** Classify ambiguous field-level diffs that deterministic logic couldn't resolve.

**Batched:** All ambiguous diffs for one student are sent in a single prompt (not one call per diff). The LLM returns a `_ValidationAgentOutput` with a `classifications` array, one entry per diff in the same order.

**Conservative defaults:**
- If the LLM fails entirely → all diffs default to `real_mismatch`.
- If the LLM returns fewer items than expected → missing entries are padded with `real_mismatch`.
- If the LLM returns an unrecognized classification label → defaults to `real_mismatch`.

#### `app/agents/reminder_agent.py` — `ReminderAgent`

**Purpose:** Draft a friendly WhatsApp reminder message for students who haven't filled the form.

**Lowest stakes agent** — only generates human-facing text, makes no data decisions. Uses a higher temperature (`LLM_REMINDER_TEMPERATURE`) for more natural language.

**Full static fallback:** If the LLM call fails for any reason, uses a hardcoded template with `{form_url}`, `{company_name}`, `{deadline}`, and `{pending_count}` substituted. The pipeline never blocks on this agent.

---

### LangGraph Pipeline

#### `app/graph/state.py` — `PipelineState`

A `TypedDict` (total=False, so all fields are optional at creation). This is the single object threaded through every pipeline node. Contains:
- **Run metadata:** `run_id`, `company_name`, `submission_deadline`.
- **Inputs:** file paths, master records, company headers, sample rows.
- **Schema:** `column_mappings`, `schema_mapping_attempts`, `schema_needs_review`.
- **Population:** `missing_fields`.
- **Forms:** `google_form_id`, `google_form_url`, `whatsapp_message`, `form_responses`.
- **Resumes:** `resume_files`, `resolved_identities`, `identity_resolution_attempts`.
- **Validation:** `validation_results`.
- **Outputs:** three output file paths.
- **Control:** `status`, `current_node`, `errors`.

No node communicates with another through anything other than this state. This ensures `run_state.json` is always a complete, replayable snapshot.

#### `app/graph/nodes.py` — 16 Node Functions

Each node receives `PipelineState`, does its work by calling services/repositories/agents, and returns a **partial dict** (only the keys it changed). LangGraph merges this into the full state. Nodes never raise — they catch exceptions and add to `state["errors"]` instead.

| Node | What it does |
|---|---|
| `load_master` | Calls `master_repository.load(file_path)`, writes `master_records` to state |
| `ingest_company_upload` | Calls `excel_service.parse_company_upload()`, writes `company_headers` + `company_sample_rows` |
| `run_schema_agent` | Calls `schema_agent.run()`, writes `column_mappings` + `schema_mapping_attempts` |
| `retry_schema_agent` | Re-runs Schema Agent on only `NEEDS_REVIEW` columns; merges with existing confident mappings |
| `populate_company_db` | Creates `CompanyRepository`, calls `populate_from_master()`, stores repo in `_company_repositories[run_id]` |
| `detect_missing_fields` | Collects all `MISSING_FIELD` mappings into `state["missing_fields"]` |
| `generate_google_form` | Calls `google_service.create_form()`, writes form ID + URL |
| `generate_whatsapp_message` | Calls `reminder_agent.draft_message()` + `whatsapp_service.format_message()` |
| `await_responses` | Calls `google_service.get_form_responses()`, writes `form_responses` |
| `parse_resumes` | Calls `pdf_service.parse_resume()` for each file, stores in `_parsed_resumes` |
| `deterministic_identity_match` | Calls `run_deterministic_match()` per resume; splits into `resolved_identities` + `_needs_ai_resolution` |
| `run_resume_identity_agent` | Calls `resume_extract_identity_agent.resolve()` for unmatched resumes |
| `merge_form_and_resume_data` | Calls `repo.merge_form_responses()` + `repo.attach_resume_data()` |
| `run_validation` | Calls `report_service.build_validation_results()` |
| `generate_reports` | Calls Excel Service + Report Service to write the 3 output files; sets `status=completed` |
| `human_review_gate` | Terminal node — sets `status=awaiting_human_review`; run resumes via POST `/runs/{id}/resume` |

#### `app/graph/edges.py` — 5 Conditional Routing Functions

Each function receives the current state and returns the name of the next node. These are the branch decisions:

| Function | Decision |
|---|---|
| `after_run_schema_agent` | Low confidence fraction > threshold **and** attempts < max_retries → `retry_schema_agent`. Exhausted retries → `human_review_gate`. Otherwise → `populate_company_db`. |
| `after_detect_missing_fields` | Missing fields exist → `generate_google_form`. None missing → skip to `run_validation`. |
| `after_await_responses` | Responses received → `parse_resumes`. No responses (stub/timeout) → `run_validation` (avoids infinite loop in MVP). |
| `after_deterministic_identity_match` | Any unresolved resumes → `run_resume_identity_agent`. All resolved → `merge_form_and_resume_data`. |
| `after_run_resume_identity_agent` | Any `needs_human_review` or `resolution_failed` → `human_review_gate`. All resolved → `merge_form_and_resume_data`. |

#### `app/graph/pipeline_graph.py` — Compiled Graph

Instantiates a `StateGraph(PipelineState)`, registers all 16 nodes, sets `load_master` as the entry point, adds all edges (linear + conditional), and calls `graph.compile()`. Exports `pipeline_graph` singleton. This is the object that `process_routes.py` calls with `.invoke(initial_state)`.

---

### Storage

#### `app/storage/file_storage.py` — `FileStorage`

Manages all filesystem layout. Provides:
- `init_run(run_id)` — creates `data/runs/{run_id}/uploads/` and `outputs/`.
- `save_upload(run_id, filename, bytes)` — writes a file to `uploads/`.
- `save_state(run_id, state_dict)` — serializes the LangGraph state to `run_state.json` (handles Pydantic models, Path objects, enums via `_make_serializable()`).
- `load_state(run_id)` — reads and returns the last saved state dict.
- `get_outputs_dir(run_id)` — used by `generate_reports` node to know where to write files.

`data/` is entirely gitignored. The `data/master/` directory is where the coordinator places the Master Database file.

---

### API Layer

#### `app/api/schemas/requests.py`

Pydantic request models for every endpoint:
- `LoadMasterRequest` — file path (defaults to `data/master/master_database.xlsx`).
- `ProcessRequest` — company name, deadline, company file path.
- `PopulateRequest` / `ValidateRequest` — just a `run_id`.
- `CorrectionItem` — type + column/field/resume/master_record identifiers for human corrections.
- `ResumeRunRequest` — list of `CorrectionItem`.

#### `app/api/schemas/responses.py`

Matching response models: `LoadMasterResponse`, `ProcessResponse`, `PopulateResponse`, `FormStatusResponse`, `ValidateResponse`, `ReportResponse`, `ResumeRunResponse`, `HealthResponse`.

#### `app/api/routes/master_routes.py`

`POST /master/load` — calls `master_repository.load(request.file_path)`, returns record count.

#### `app/api/routes/form_routes.py`

- `POST /forms/upload` — generates a new `run_id`, saves the uploaded file via `file_storage.save_upload()`, returns `run_id` + saved path. This is typically the **first API call** a coordinator makes.
- `GET /forms/{run_id}` — reads `google_form_url` and `whatsapp_message` from `_run_states`.

#### `app/api/routes/process_routes.py`

- `POST /process` — validates that Master DB is loaded, creates initial `PipelineState`, adds `_run_pipeline()` as a background task (runs in a thread pool executor), returns `run_id` immediately.
- `GET /process/{run_id}/status` — reads from `_run_states` dict (in-memory).

`_run_states` is currently in-memory (lost on server restart). The compiled state is also saved to `run_state.json` via `file_storage.save_state()` for debugging.

#### `app/api/routes/populate_routes.py`

`POST /populate` — runs schema mapping only, without starting the full pipeline. Useful to preview column mappings before committing to a run.

#### `app/api/routes/validate_routes.py`

`POST /validate` — re-runs `report_service.build_validation_results()` against the in-memory company repository. Used after a coordinator provides corrections at `human_review_gate`.

#### `app/api/routes/report_routes.py`

- `GET /reports/{run_id}` — returns all three output file paths from state.
- `GET /reports/{run_id}/download?report_type=...` — serves the file as a `FileResponse` download. `report_type` is one of `populated_database`, `validation_report`, `mismatch_report`.
- `POST /runs/{run_id}/resume` — applies `CorrectionItem` list to column mappings and identity resolutions in state, sets status back to `running`.

---

## Data Flow Diagram (Simplified)

```
.env ──────────────────────────────────────────────────────────────────►
                                                                config.py
                                                                    │
                                                         ┌──────────▼──────────┐
              master_database.xlsx ──► ExcelService ──► MasterRepository (indices)
                                                                    │
              company_upload.xlsx ──► ExcelService ─────────────────┤
                                     (headers + 5 rows)             │
                                              │                     │
                                              ▼                     │
                                       SchemaAgent ◄── VectorRepository ◄── ChromaDB
                                       (+ LLMService)               │
                                              │ ColumnMappings      │
                                              ▼                     ▼
                                       CompanyRepository.populate_from_master()
                                              │
                                    ┌─────────┴──────────┐
                            missing fields?           all fields present
                                    │                       │
                                    ▼                       │
                            GoogleService (form)            │
                            ReminderAgent (msg)             │
                                    │                       │
                            form responses arrive           │
                                    │                       │
                            PDFService (parse resumes)      │
                                    │                       │
                            identity_hierarchy              │
                              (deterministic)               │
                                    │ failed?               │
                                    ▼                       │
                            ResumeExtractIdentityAgent      │
                            (+ LLMService)                  │
                                    │                       │
                                    └──────────┬────────────┘
                                               ▼
                                    CompanyRepository.merge()
                                               │
                                               ▼
                              ReportService.build_validation_results()
                                    │
                          ┌─────────┤
                          │         ▼
                          │    ValidationAgent (ambiguous diffs)
                          │    (+ LLMService)
                          │         │
                          └─────────┘
                                    ▼
                          ExcelService + ReportService
                          write 3 output Excel files
```

---

## Typical API Call Sequence

```bash
# 1. Load the Master Database (once per session, or on change)
curl -X POST http://localhost:8000/api/v1/master/load \
  -H "Content-Type: application/json" \
  -d '{"file_path": "data/master/master_database.xlsx"}'

# 2. Upload company Excel template
curl -X POST http://localhost:8000/api/v1/forms/upload \
  -F "file=@/path/to/company_template.xlsx"
# → {"run_id": "r_abc123", "file_path": "data/runs/r_abc123/uploads/..."}

# 3. Start the pipeline
curl -X POST http://localhost:8000/api/v1/process \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "Acme Corp",
    "submission_deadline": "2026-08-15T18:00:00Z",
    "company_file_path": "data/runs/r_abc123/uploads/company_template.xlsx"
  }'
# → {"run_id": "r_abc123", "status": "running"}

# 4. Poll for completion
curl http://localhost:8000/api/v1/process/r_abc123/status

# 5. Download the populated database
curl "http://localhost:8000/api/v1/reports/r_abc123/download?report_type=populated_database" \
  -o populated_database.xlsx
```

---

## Gotchas & Known Limitations

- **Ollama must be running** before schema mapping or any AI agent is used. The server starts fine without it, but pipeline runs will fail at `run_schema_agent`. Configure `OLLAMA_BASE_URL` in `.env`.
- **Pull both models** before first use: `ollama pull llama3.1 && ollama pull nomic-embed-text`.
- **Master DB must be loaded first.** `POST /process` will return HTTP 400 if `POST /master/load` has not been called in the current session. The master DB is in-memory only and does not survive server restarts.
- **`_run_states` is in-memory.** Pipeline status is lost on server restart. The `run_state.json` file persists to disk for each run but is not automatically re-loaded into the in-memory dict. For production, back `_run_states` with a database or `file_storage.load_state()`.
- **Enrollment number regex** in `constants.py` is institution-specific. Pattern `\b\d{2}[A-Z]{2,4}\d{2,4}\b` matches formats like `21CS045`. Adjust if your format differs.
- **Google integration is stubbed.** `create_form()` returns a fake URL; `get_form_responses()` returns `[]`. Enable with `GOOGLE_INTEGRATION_ENABLED=true` + service account credentials.
- **Resume downloading is stubbed.** In the current MVP, `resume_files` in the pipeline state is always empty unless you manually populate it before calling `POST /process`.
- **`POST /runs/{run_id}/resume`** applies corrections to in-memory state but does not yet re-invoke the LangGraph from `merge_form_and_resume_data`. After resuming, manually call `POST /validate` to re-run validation with the corrected data.


# TNP Database Automation Platform

AI-powered automation for Training & Placement (TNP) cell workflows. Given a Master Student Database and an arbitrary company Excel template, the system automatically maps columns, fills data from the master records, generates a Google Form for missing fields, parses student resumes, resolves identities, validates data, and produces three deliverable files: **Populated Company Database**, **Validation Report**, and **Mismatch Report**.

---

## Quick Start

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env: set OLLAMA_BASE_URL to your server

# 2. Start the server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 3. Open interactive API docs
# http://localhost:8000/docs

# 4. Run unit tests
pytest tests/ -v
```

---

## Developer's Reading Guide

> **Start here if you are new to this codebase.** Follow the steps in order. Each step tells you what file to open, what to focus on, and what you should understand before moving to the next one.

---

### Step 0 — Clone and get running (15 min)

Before reading any code, get the server up so you can see it respond. Watching real log output while you read code is far more useful than reading in the abstract.

```bash
cp .env.example .env
# Open .env and set OLLAMA_BASE_URL to your Ollama server URL
# (You can skip this for now — the server will start fine, agents will just fail)

cd tnp_backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000/docs` in your browser. You should see the Swagger UI with all 11 endpoints. Open `http://localhost:8000/api/v1/health` — you should get a JSON response.

**Goal:** Server running, `/docs` open, `/health` returns `{"status":"ok"}`.

---

### Step 1 — Read `app/config.py` (5 min)

**Why first?** Every other file imports `from app.config import settings`. You need to know what knobs exist before you can understand why code behaves differently in different environments.

**What to look for:**
- There is one `settings` object, loaded once at import time from `.env`.
- Notice the threshold fields: `column_mapping_confidence_threshold`, `identity_confidence_threshold`, `schema_agent_max_retries`. These control when the pipeline calls the LLM vs. falls back to a human.
- Notice `google_integration_enabled=False` by default. This means Google service methods are all stubs.

**After this you know:** What environment variables exist, what their defaults are, and which ones you'd need to change to connect real services.

---

### Step 2 — Read `app/utils/constants.py` (5 min)

**Why second?** This file defines the domain vocabulary. `MASTER_DB_FIELDS` is the dictionary that the entire Schema Agent, Vector Index, and Excel Service all revolve around.

**What to look for:**
- The 17 canonical field names (e.g. `enrollment_number`, `cgpa`). Every column in every company Excel file will eventually be mapped to one of these names — or marked as missing.
- `ENROLLMENT_NUMBER_PATTERN` — the regex for your institution's roll number format. **If you are adapting this for a different college, this is the first thing you change.**
- The output filenames at the bottom (`populated_company_db.xlsx` etc.) — these are the three files the system produces.

**After this you know:** The fixed schema the whole system talks about.

---

### Step 3 — Read `app/main.py` (10 min)

**Why third?** This is the true entry point. Reading it shows you what order things are initialized in, and where every piece gets wired together.

**What to look for:**

```
uvicorn starts → lifespan() runs → configure_logging() →
  create data/ directories →
  vector_repository.index_master_fields() [pre-warm ChromaDB] →
  server starts accepting requests
```

- The `lifespan()` context manager runs **before** the first HTTP request. If ChromaDB pre-warming fails (Ollama not running), it logs a warning and continues — the server does not crash.
- The six `app.include_router(...)` calls tell you all route files exist and are active. Note the prefixes — `/api/v1/process` vs `/api/v1/forms` etc.

**After this you know:** How the server boots, what runs at startup, and where each URL prefix is registered.

---

### Step 4 — Read the Models (20 min)

**Why now?** Before reading any logic, understand the data shapes. Models are read-only — no business logic, just fields. Reading them gives you a mental picture of what flows between all the other components.

**Read them in this order:**

| File | What it represents | Key fields to notice |
|---|---|---|
| `models/master_record.py` | One verified student | `enrollment_number` + `name` required; everything else optional; `extra` dict for unknown columns |
| `models/company_record.py` | One row being built for a company | `data` dict + `missing_field_values` dict + `RecordStatus` enum |
| `models/column_mapping.py` | Schema Agent's verdict on one column | `status` enum: `mapped` / `missing_field` / `needs_review` / `skipped` |
| `models/resume_data.py` | A parsed resume + its identity resolution | Two sections: extracted fields + resolution metadata (`needs_human_review` flag) |
| `models/validation_result.py` | Validation outcome for one student | `FieldClassification` with `DiffClassification` enum (`likely_typo` / `acceptable_variation` / `real_mismatch`) |
| `models/run.py` | Run lifecycle metadata | `RunStatus` enum + summary stats |

**After this you know:** The shapes of all data moving through the system. When you later read a service or agent, you'll recognize the models it uses.

---

### Step 5 — Read `app/graph/state.py` (5 min)

**Why now?** `PipelineState` is the single object that carries *all* data through the pipeline. Every node reads from it and writes back to it. Read it once and keep it as a reference.

**What to look for:**
- It is a flat `TypedDict` with `total=False` — all fields are optional so the state can be partially filled at any step.
- Group the fields mentally into sections: run metadata → inputs → schema results → form/collection results → resume results → validation results → output paths → control flags.
- The `status` field (`running` / `awaiting_human_review` / `completed` / `failed`) and `current_node` are the two fields you'd check when polling a run.

**After this you know:** Everything that can exist in a pipeline's working memory.

---

### Step 6 — Read the Services (30–40 min)

**Why now?** Services are the workhorses. They are pure utilities — stateless, no pipeline awareness, easy to read independently. Understanding them gives you confidence that you know what each tool can do before you see it being used.

**Read them in this order (easiest → most complex):**

1. **`services/embedding_service.py`** — just wraps `OllamaEmbeddings`. Read to understand: `embed(texts)` returns a list of float vectors; `embed_query(text)` returns one vector. Lazy-init pattern.

2. **`services/vector_service.py`** — wraps ChromaDB. Read to understand: `upsert(collection, ids, texts, metadatas)` stores documents as vectors; `query_similar(collection, query_text, top_k)` finds closest matches by cosine distance. Pure similarity search — no domain knowledge.

3. **`services/llm_service.py`** — the core LLM wrapper. Read carefully:
   - `generate_structured()` calls the LLM, strips markdown fences, parses JSON, validates against a Pydantic schema. If it fails, it appends a correction message to the conversation and retries.
   - The `_extract_json()` method handles the common case of the LLM wrapping its answer in ` ```json ... ``` ` fences.

4. **`services/excel_service.py`** — read `load_master_database()` to see how the Master DB is normalized. Note the `MASTER_COLUMN_ALIASES` dict — this is how common header variations like `roll_no` or `mobile` get mapped to canonical names.

5. **`services/pdf_service.py`** — straightforward PyMuPDF usage + three regex extractors. The `ENROLLMENT_NUMBER_PATTERN` from `constants.py` is used here.

6. **`services/google_service.py`** — read it to understand the interface, then notice all three methods are stubs behind `if not self._enabled`. The `TODO` comments show exactly what the real implementation would do.

7. **`services/whatsapp_service.py`** — read the `WhatsAppSender` Protocol to understand the future extension point.

8. **`services/report_service.py`** — the most complex service. Focus on `compute_diffs()` and `classify_diffs_deterministically()`. Note: deterministic classification handles the easy cases (one side empty → mismatch; alphanumeric-equal → acceptable variation). Everything genuinely ambiguous is passed to the Validation Agent.

**After this you know:** What every low-level tool does and what it returns.

---

### Step 7 — Read the Repositories (20 min)

Repositories sit between services and the pipeline. They own data access patterns and indices.

**Read in this order:**

1. **`repositories/vector_repository.py`** — thin wrapper: `index_master_fields()` upserts all 17 `MASTER_DB_FIELDS` entries into ChromaDB. `query_similar_fields()` delegates to vector_service. This is what the Schema Agent calls.

2. **`repositories/master_repository.py`** — read `_build_indices()` to see how the three hash maps (`_by_enrollment`, `_by_phone`, `_by_email`) are constructed. These enable O(1) deterministic matching. Note: singleton, loaded once per session.

3. **`repositories/company_repository.py`** — read `populate_from_master()` first, then `merge_form_responses()`, then `attach_resume_data()`. These three methods represent the three enrichment phases a company record goes through. Note: created fresh per run via `new_company_repository()` — not a singleton.

4. **`repositories/collection_repository.py`** — read `_normalize()` to see how raw Google Sheet headers get mapped to canonical field names.

**After this you know:** How data is stored, indexed, and progressively enriched during a run.

---

### Step 8 — Read the Agents (30 min)

Now you have the full foundation to understand why the agents are designed the way they are.

**Read in this order (simplest → most complex):**

1. **`agents/reminder_agent.py`** — start here. Simplest agent: just drafts text, never makes data decisions. Notice the full static fallback if LLM fails. Good pattern to understand before the more complex agents.

2. **`agents/schema_agent.py`** — read `_map_column()` to see the two-stage flow:
   - Stage 1: `vector_repository.query_similar_fields()` → top-5 candidates (embedding lookup, no LLM yet)
   - Stage 2: `llm_service.generate_structured()` with `_ColumnMappingOutput` → pick the best candidate
   
   The two-stage design is important: the LLM can only pick from the candidates list, so it can never hallucinate a field name that doesn't exist in the Master DB.

3. **`agents/validation_agent.py`** — read `classify()` to see batched prompting (all diffs for one student in one call). Notice the conservative defaults: any LLM failure → all diffs become `real_mismatch`.

4. **`agents/resume_extract_identity_agent.py`** — read `resolve()`. Notice the confidence gate: even if the LLM returns a match, if `confidence < IDENTITY_CONFIDENCE_THRESHOLD` the result is flagged for human review rather than auto-accepted. This is the most safety-critical agent.

**After this you know:** When and why LLM is invoked at each decision point, and what the fallback is when it fails.

---

### Step 9 — Read the LangGraph Pipeline (30 min)

Now you can read the pipeline itself. You already know every component it calls.

**Read in this order:**

1. **`graph/state.py`** — you've already read this; skim it again as a refresher.

2. **`graph/nodes.py`** — read each node function. They are short (10–30 lines each). The pattern is always:
   ```
   def some_node(state: PipelineState) -> dict:
       try:
           result = some_service.do_thing(state["some_field"])
           return {"output_field": result, "current_node": "some_node"}
       except Exception as exc:
           return {"status": "failed", "errors": [..., str(exc)]}
   ```
   Pay attention to `populate_company_db` — it stores the `CompanyRepository` in the `_company_repositories` dict keyed by `run_id`. This is the only global state that lives outside of `PipelineState`.

3. **`graph/edges.py`** — read each routing function. These are where the `if/else` branching happens. The most important one is `after_run_schema_agent` — it decides whether to retry, escalate to human review, or proceed.

4. **`graph/pipeline_graph.py`** — read last. This is just assembly: register nodes, set entry point, add edges. The resulting `pipeline_graph` singleton is what the API calls with `.invoke(initial_state)`.

**Draw the graph on paper as you read** — start with `load_master` at the top, draw arrows for each `add_edge()`, draw branches for each `add_conditional_edges()`. After drawing it you will have the full execution flow memorized.

**After this you know:** The complete pipeline: what runs in what order, when it branches, and where it can pause for human input.

---

### Step 10 — Read the Storage Layer (10 min)

**`storage/file_storage.py`** — read this after the graph. It's simpler than it looks: just path helpers + JSON serialization. The most interesting method is `_make_serializable()` — it recursively converts Pydantic models and `Path` objects so the state dict can be JSON-serialized.

**After this you know:** How run state is persisted to disk and where each run's files live.

---

### Step 11 — Read the API Layer (20 min)

Now read the API as the final layer on top of everything you understand.

**Read schemas first, then routes:**

1. **`api/schemas/requests.py`** + **`api/schemas/responses.py`** — scan through all models. They are simple Pydantic models, one per endpoint.

2. **`api/routes/master_routes.py`** — the simplest route. One endpoint, calls one repository method.

3. **`api/routes/form_routes.py`** — read `upload_company_file()` first. This is the first call a coordinator makes. Notice it generates the `run_id` here.

4. **`api/routes/process_routes.py`** — the most important route. Read `start_process()`:
   - Checks master DB is loaded.
   - Creates `initial_state` (the full `PipelineState` dict with all fields initialized).
   - Adds `_run_pipeline()` as a background task → returns immediately with `run_id`.
   - `_run_pipeline()` calls `pipeline_graph.invoke(initial_state)` in a thread pool executor (so async FastAPI doesn't block).

5. **`api/routes/populate_routes.py`**, **`validate_routes.py`**, **`report_routes.py`** — read in any order. They are smaller and follow the same pattern.

**After this you know:** The complete system from HTTP request to pipeline invocation to file download.

---

### Step 12 — Do a Real Trace (hands-on, ~1 hour)

By this point you understand every file. Now make it real by tracing one actual request through the system.

```bash
# 1. Load a test master DB
curl -X POST http://localhost:8000/api/v1/master/load \
  -H "Content-Type: application/json" \
  -d '{"file_path": "data/master/master_database.xlsx"}'

# 2. Upload a company file
curl -X POST http://localhost:8000/api/v1/forms/upload \
  -F "file=@/path/to/company_template.xlsx"

# 3. Start the pipeline — watch the server logs in the terminal
curl -X POST http://localhost:8000/api/v1/process \
  -H "Content-Type: application/json" \
  -d '{"company_name":"Acme","submission_deadline":"2026-09-01T00:00:00Z","company_file_path":"data/runs/r_xxx/uploads/company_template.xlsx"}'

# 4. Poll status
curl http://localhost:8000/api/v1/process/r_xxx/status
```

Watch the server logs. You will see log lines like:
```
[r_abc123] Node: load_master
[r_abc123] Node: ingest_company_upload
[r_abc123] Node: run_schema_agent
Schema Agent: 12 mapped, 2 missing, 1 need review out of 15 columns.
...
```

Each log line maps directly to a node function in `graph/nodes.py`.

**After this you know:** The system end-to-end, from your own live trace.

---

### Quick Reference: What Calls What

```
main.py
  └─► config.py              (settings singleton, imported everywhere)
  └─► utils/logging.py       (configure_logging)
  └─► repositories/vector_repository.py  (index_master_fields on startup)
  └─► api/routes/*.py        (all route handlers)

routes/process_routes.py
  └─► graph/pipeline_graph.py   (pipeline_graph.invoke)
       └─► graph/nodes.py       (16 node functions)
            └─► services/llm_service.py          (agents)
            └─► services/excel_service.py         (load_master, write output)
            └─► services/pdf_service.py           (parse_resumes)
            └─► services/google_service.py        (form + responses, stubbed)
            └─► services/whatsapp_service.py      (format message)
            └─► services/report_service.py        (build_validation_results, write reports)
            └─► repositories/master_repository.py (master records)
            └─► repositories/company_repository.py (company records per run)
            └─► repositories/vector_repository.py (field index)
            └─► agents/schema_agent.py
                  └─► repositories/vector_repository.py (query_similar_fields)
                  └─► services/llm_service.py     (generate_structured)
            └─► agents/resume_extract_identity_agent.py
                  └─► services/llm_service.py     (generate_structured)
            └─► agents/validation_agent.py
                  └─► services/llm_service.py     (generate_structured)
            └─► agents/reminder_agent.py
                  └─► services/llm_service.py     (generate_text)
       └─► graph/edges.py     (5 routing functions)
  └─► storage/file_storage.py (init_run, save_state, save_upload)
```

---

## How a Run Works (End-to-End Flow)

```
Coordinator                     API                      LangGraph Pipeline
──────────────────────────────────────────────────────────────────────────────

1. Load Master DB    ──►  POST /master/load
                                │
                                ▼ master_repository.load()

2. Upload company    ──►  POST /forms/upload
   Excel file                   │
                                ▼ file_storage.save_upload()
                                  returns run_id

3. Start pipeline    ──►  POST /process
                                │
                                ▼ background task → LangGraph invoked
                                │
                          ┌─────▼─────────────────────────────────────────┐
                          │  load_master                                   │
                          │      └─► Load MasterRecords into state         │
                          │  ingest_company_upload                         │
                          │      └─► ExcelService reads headers + 5 rows   │
                          │  run_schema_agent                              │
                          │      └─► EmbeddingService: embed each column   │
                          │      └─► VectorRepository: top-k candidates    │
                          │      └─► LLMService: pick best match → ColumnMapping │
                          │      ┌─[too many low-confidence?]              │
                          │      ├─► retry_schema_agent (max 2 retries)    │
                          │      └─► human_review_gate (if retries exhausted) │
                          │  populate_company_db                           │
                          │      └─► CompanyRepository.populate_from_master() │
                          │  detect_missing_fields                         │
                          │      ┌─[missing fields exist?]                 │
                          │      ├─► generate_google_form                  │
                          │      │       └─► GoogleService.create_form()   │
                          │      │   generate_whatsapp_message             │
                          │      │       └─► ReminderAgent.draft_message() │
                          │      │   await_responses                       │
                          │      │       └─► GoogleService.get_form_responses() │
                          │      │       ┌─[responses received?]           │
                          │      │       ├─► parse_resumes                 │
                          │      │       │       └─► PDFService.parse_resume() │
                          │      │       │   deterministic_identity_match  │
                          │      │       │       └─► identity_hierarchy chain │
                          │      │       │       ┌─[unresolved resumes?]   │
                          │      │       │       ├─► run_resume_identity_agent │
                          │      │       │       │   └─► LLMService → confidence gate │
                          │      │       │       └─► merge_form_and_resume_data │
                          │      │       └─[no responses / stub] ──────────┤
                          │      └─[no missing fields] ─────────────────── ┤
                          │  run_validation                                 │
                          │      └─► ReportService.build_validation_results() │
                          │      └─► ValidationAgent.classify() for diffs  │
                          │  generate_reports                               │
                          │      └─► Write 3 Excel output files             │
                          └─────────────────────────────────────────────────┘

4. Check status      ──►  GET /process/{run_id}/status
5. Get form link     ──►  GET /forms/{run_id}
6. Download outputs  ──►  GET /reports/{run_id}/download?report_type=populated_database
```

---

## Configuration

Copy `.env.example` → `.env` and set these variables:

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL of your Ollama server |
| `OLLAMA_MODEL` | `llama3.1` | Chat model for agents |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model for schema mapping |
| `LLM_TEMPERATURE` | `0.1` | Temperature for schema/validation agents |
| `LLM_REMINDER_TEMPERATURE` | `0.3` | Higher temperature for message drafting |
| `COLUMN_MAPPING_CONFIDENCE_THRESHOLD` | `0.7` | Minimum confidence to auto-accept a mapping |
| `IDENTITY_CONFIDENCE_THRESHOLD` | `0.75` | Minimum AI confidence to auto-accept resume identity |
| `SCHEMA_AGENT_MAX_RETRIES` | `2` | How many times to retry poor schema mappings |
| `GOOGLE_INTEGRATION_ENABLED` | `false` | Set `true` to use real Google Forms/Drive |
| `DATA_DIR` | `./data` | Root directory for all run data |
| `LOG_LEVEL` | `INFO` | DEBUG / INFO / WARNING / ERROR |

---

## API Reference

All endpoints are prefixed with `/api/v1`. Interactive docs at `/docs`.

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check — confirms server + config |
| POST | `/master/load` | Load Master Database from an Excel/CSV path |
| POST | `/forms/upload` | Upload company Excel; returns `run_id` |
| POST | `/process` | Start full async pipeline; returns `run_id` immediately |
| GET | `/process/{run_id}/status` | Poll pipeline progress |
| POST | `/populate` | Schema mapping + population preview (no form) |
| GET | `/forms/{run_id}` | Get generated Google Form URL + WhatsApp message |
| POST | `/validate` | Re-run validation (after human corrections) |
| GET | `/reports/{run_id}` | Get output file paths for a completed run |
| GET | `/reports/{run_id}/download` | Download one of the three output files |
| POST | `/runs/{run_id}/resume` | Resume a run paused at human_review_gate |

---

## Full Project Structure

```
tnp_backend/
│
├── .env.example               ← All env vars documented
├── .gitignore
├── pyproject.toml             ← Python project + dependency declarations
├── README.md                  ← This file
│
├── data/                      ← Runtime data (gitignored)
│   ├── master/                ← Place your master_database.xlsx here
│   └── runs/
│       └── <run_id>/
│           ├── uploads/       ← Uploaded company Excel + downloaded resumes
│           ├── outputs/       ← Generated Excel outputs
│           └── run_state.json ← Serialized pipeline snapshot
│
├── tests/
│   ├── fixtures/README.md     ← Instructions for creating test fixtures
│   ├── unit/
│   │   ├── test_identity_hierarchy.py
│   │   └── test_report_service.py
│
└── app/
    ├── main.py                ← FastAPI app + startup hooks  [ENTRY POINT]
    ├── config.py              ← Pydantic Settings singleton
    │
    ├── utils/
    │   ├── constants.py       ← Master DB field catalogue, regex patterns, status codes
    │   ├── logging.py         ← Loguru setup + run-scoped logger
    │   └── identity_hierarchy.py  ← Deterministic enrollment→phone→email matching
    │
    ├── models/
    │   ├── master_record.py   ← MasterRecord (authoritative student row)
    │   ├── company_record.py  ← CompanyRecord + RecordStatus enum (in-progress row)
    │   ├── column_mapping.py  ← ColumnMapping + MappingStatus enum
    │   ├── resume_data.py     ← ResumeData (parsed PDF + identity resolution)
    │   ├── validation_result.py ← ValidationResult, FieldClassification, DiffClassification
    │   └── run.py             ← Run + RunStatus (run lifecycle metadata)
    │
    ├── services/
    │   ├── llm_service.py         ← ChatOllama wrapper: generate_text, generate_structured
    │   ├── embedding_service.py   ← OllamaEmbeddings wrapper: embed, embed_query
    │   ├── vector_service.py      ← ChromaDB PersistentClient: upsert, query_similar
    │   ├── excel_service.py       ← Pandas+OpenPyXL: load master, parse upload, write output
    │   ├── pdf_service.py         ← PyMuPDF: extract text + regex email/phone/enrollment
    │   ├── google_service.py      ← STUB: create_form, get_form_responses, download_resumes
    │   ├── whatsapp_service.py    ← Format + (stub) send WhatsApp messages
    │   └── report_service.py      ← Build ValidationResults, write 3 Excel reports
    │
    ├── repositories/
    │   ├── master_repository.py      ← In-memory Master DB with enrollment/phone/email indices
    │   ├── company_repository.py     ← Per-run Company DB: populate, merge, attach, export
    │   ├── vector_repository.py      ← ChromaDB collection lifecycle for Master DB fields
    │   └── collection_repository.py  ← Read + normalize Google Form responses
    │
    ├── agents/
    │   ├── schema_agent.py                    ← Map company columns → Master DB fields
    │   ├── resume_extract_identity_agent.py   ← AI fallback for resume identity resolution
    │   ├── validation_agent.py                ← Classify ambiguous field diffs
    │   └── reminder_agent.py                  ← Draft WhatsApp reminder messages
    │
    ├── graph/
    │   ├── state.py           ← PipelineState TypedDict (all fields threaded through nodes)
    │   ├── nodes.py           ← 16 LangGraph node functions (one per pipeline step)
    │   ├── edges.py           ← 5 conditional routing functions (branch logic)
    │   └── pipeline_graph.py  ← Assembles + compiles the StateGraph; exports singleton
    │
    ├── storage/
    │   ├── file_storage.py    ← Per-run directory layout, state persistence to JSON
    │   └── chroma_store/      ← ChromaDB on-disk persistence (auto-created)
    │
    └── api/
        ├── schemas/
        │   ├── requests.py    ← Pydantic request models for every endpoint
        │   └── responses.py   ← Pydantic response models for every endpoint
        └── routes/
            ├── master_routes.py    ← POST /master/load
            ├── process_routes.py   ← POST /process, GET /process/{run_id}/status
            ├── populate_routes.py  ← POST /populate
            ├── form_routes.py      ← GET /forms/{run_id}, POST /forms/upload
            ├── validate_routes.py  ← POST /validate
            └── report_routes.py    ← GET /reports/{run_id}, /download, POST /runs/{id}/resume
```

---

## File-by-File Reference

Each section follows the actual execution order from server startup to pipeline completion.

---

### Startup Chain

#### `app/main.py` — Entry Point

The very first file Python executes. Does four things in order:

1. **Imports** `config.py`, all six routers, and `vector_repository`.
2. **`lifespan()` hook** (runs before the server accepts requests):
   - Calls `configure_logging()` to set up Loguru.
   - Creates `data/master/`, `data/runs/` directories if missing.
   - Calls `vector_repository.index_master_fields()` to pre-warm ChromaDB with the Master DB field catalogue. If Ollama is not running yet, it logs a warning and continues — the Schema Agent will retry on first use.
3. **Creates the FastAPI `app`** with CORS middleware (allow all origins).
4. **Registers all routers** under the `/api/v1` prefix, plus the `/health` and `/` endpoints.

#### `app/config.py` — Settings Singleton

Loaded by `main.py` at import time. Reads all environment variables from `.env` using Pydantic Settings. Exposes a single `settings` object imported everywhere. Validates types and ranges (e.g. `llm_temperature` must be 0.0–2.0). Every other file does `from app.config import settings` — nothing is hardcoded.

---

### Utilities (loaded at import time, no side effects)

#### `app/utils/constants.py`

Defines pure data that nothing else computes:
- `MASTER_DB_FIELDS` — the 17 canonical field names + human descriptions. This dict is the single source of truth for what the Master Database can contain. The Schema Agent maps company columns to these names; the embedding index is built from these descriptions.
- `ENROLLMENT_NUMBER_PATTERN` — regex for institution-specific roll numbers (e.g. `21CS045`). Used by the PDF Service and identity hierarchy. **Adjust this if your institution uses a different format.**
- `FORM_IDENTITY_FIELDS`, `PII_FIELDS`, `VALIDATION_CLASSIFICATIONS` — used by agents and reports.
- `OUTPUT_POPULATED_DB`, `OUTPUT_VALIDATION_REPORT`, `OUTPUT_MISMATCH_REPORT` — standardized output filenames.

#### `app/utils/logging.py`

Two functions:
- `configure_logging(level)` — removes Loguru's default handler, adds a stderr sink with colour formatting. Called once by `main.py` lifespan.
- `get_run_logger(run_id)` — returns a logger pre-bound with `run_id` context so every log line from a pipeline run is traceable.

#### `app/utils/identity_hierarchy.py`

Pure functions implementing the three-step deterministic student matching algorithm (FR-10). Called by `nodes.py` inside the `deterministic_identity_match` node.

**Algorithm:**
1. Normalize and look up `enrollment_number` in all Master records. If exactly one match → return it. If >1 → fall through.
2. Normalize and look up `phone_number` (last 10 digits). If exactly one match → return it.
3. Normalize and look up `email` (lowercase + strip). If exactly one match → return it.
4. If all three fail → return `matched=False` to signal the AI agent must be invoked.

Returns a `DeterministicMatchResult` dataclass. Also exports `normalize_phone`, `normalize_email`, `normalize_enrollment` — used by `master_repository.py` to build indices.

---

### Domain Models

All models are Pydantic v2 `BaseModel`. They carry data through the system; they contain no business logic beyond field validation.

#### `app/models/master_record.py` — `MasterRecord`

One row from the Master Database. Two fields are required (`enrollment_number`, `name`). All others (email, phone, branch, CGPA, etc.) are optional. An `extra` dict catches any additional columns in the actual file beyond the known 17. `to_flat_dict()` merges known + extra fields into one dict for comparison and output.

#### `app/models/company_record.py` — `CompanyRecord` + `RecordStatus`

One row in the Company Database for a specific run. Starts as `PENDING`, progresses through `POPULATED` → `COMPLETE`. Contains:
- `data` — company column headers mapped to values from the Master DB.
- `missing_field_values` — values filled in via Google Form.
- Resume resolution metadata (file, matched enrollment, confidence, method).
- `RecordStatus` enum: `pending`, `populated`, `complete`, `incomplete`, `needs_review`.

#### `app/models/column_mapping.py` — `ColumnMapping` + `MappingStatus`

One mapping produced by the Schema Agent per company column. Key fields:
- `company_column` — original header from the company's file.
- `mapped_field` — canonical Master DB field name it maps to (or `None`).
- `confidence` — 0.0–1.0 score from the LLM.
- `status` — `mapped` / `missing_field` / `needs_review` / `skipped`.
- `review_candidates` — top-k shortlist shown to human reviewers.

#### `app/models/resume_data.py` — `ResumeData`

Output of resume processing. Contains extracted contact fields (email, phone, enrollment from PDF text), plus identity resolution metadata (which Master record it resolved to, what method was used, confidence score, and flags for `needs_human_review` or `resolution_failed`).

#### `app/models/validation_result.py` — `ValidationResult`, `FieldClassification`, `DiffClassification`

Per-student validation outcome. `FieldClassification` represents one field-level diff:
- `classification` — `likely_typo` / `acceptable_variation` / `real_mismatch`.
- `agent_classified` — `True` if the LLM decided; `False` if deterministic code decided.

`ValidationResult` aggregates all field classifications for one student plus pass/fail, counts, and review flags.

#### `app/models/run.py` — `Run` + `RunStatus`

Serializable run lifecycle metadata (company name, deadline, status, timestamps, output paths, summary statistics). Serialized to `run_state.json` after every pipeline node for resumability.

---

### Services

Services are stateless utilities. Each is a singleton imported where needed. They know nothing about the pipeline or LangGraph — they just do one job well.

#### `app/services/llm_service.py` — `LLMService`

The single point of contact with Ollama. Two public methods:

- `generate_text(system, user)` — plain string output. Used by the Reminder Agent for WhatsApp message drafts.
- `generate_structured(system, user, schema, max_retries)` — calls the LLM, strips markdown fences, parses JSON, validates against a Pydantic schema. If parsing or validation fails, it appends a correction turn to the conversation and retries up to `max_retries` times. Raises `LLMServiceError` after all retries. Used by the Schema Agent, Resume Identity Agent, and Validation Agent.

Internally maintains two `ChatOllama` instances — one at `LLM_TEMPERATURE` (for data decisions) and one at `LLM_REMINDER_TEMPERATURE` (for message drafting).

#### `app/services/embedding_service.py` — `EmbeddingService`

Thin wrapper around `OllamaEmbeddings`. Lazy-initializes the client on first use. Two methods: `embed(texts)` for bulk documents, `embed_query(text)` for single queries. Raises `EmbeddingServiceError` with a human-readable message if Ollama is unreachable or the model is not pulled.

#### `app/services/vector_service.py` — `VectorService`

Owns the ChromaDB `PersistentClient` at `app/storage/chroma_store/`. Provides `upsert(collection, ids, texts, metadatas)` and `query_similar(collection, query_text, top_k)`. Uses cosine similarity (`hnsw:space=cosine`). Distances are 0 (identical) to 1 (orthogonal). Completely unaware of what the data means — just stores and retrieves vectors.

#### `app/services/excel_service.py` — `ExcelService`

All Excel/CSV I/O. Three methods:

- `load_master_database(path)` — reads the Master DB with Pandas, normalizes column names (lowercase + snake_case), applies column aliases (e.g. `roll_no` → `enrollment_number`), validates required columns, returns `list[MasterRecord]`.
- `parse_company_upload(path)` — reads the company file, preserves original header capitalisation exactly (critical — the Schema Agent needs them as-is), returns `(headers, sample_rows[:5])`.
- `write_populated_database(path, headers, rows)` — writes output with OpenPyXL. Applies bold white text + dark green fill to the header row.

#### `app/services/pdf_service.py` — `PDFService`

Uses PyMuPDF (`fitz`) to open PDF files and extract text page by page. Then runs three regex extractors:
- Email: standard email pattern.
- Phone: India-aware pattern (country code, 10-digit mobile) with fallback to generic groups. Returns last 10 digits only.
- Enrollment number: uses `ENROLLMENT_NUMBER_PATTERN` from `constants.py`.

Returns a dict with `file_path`, `raw_text`, `email`, `phone`, `enrollment_number`. The `raw_text` is passed to the AI agent if deterministic matching fails.

#### `app/services/google_service.py` — `GoogleService` *(stub)*

Defines the full interface for Google Forms, Sheets, and Drive. When `GOOGLE_INTEGRATION_ENABLED=false` (the default), all methods return safe stubs:
- `create_form()` → returns a fake form ID and URL.
- `get_form_responses()` → returns `[]`.
- `download_resume_files()` → returns `[]`.

The real implementation is documented in `TODO` comments inside each method. To enable: set `GOOGLE_INTEGRATION_ENABLED=true`, provide a service account JSON, and install `pip install tnp-automation-platform[google]`.

#### `app/services/whatsapp_service.py` — `WhatsAppService`

Formats the final WhatsApp message string. In MVP, sending is a no-op (the `StubSender` just logs). Uses the `WhatsAppSender` Protocol so a real Twilio/WhatsApp Business backend can be plugged in later without changing calling code. `format_message()` substitutes the actual form URL into the Reminder Agent's draft or falls back to a static template if the agent provided nothing.

#### `app/services/report_service.py` — `ReportService`

The most complex service. Three responsibilities:

1. **`build_validation_results(master, company, mappings, agent)`** — for every company record:
   - Looks up the matching Master record by enrollment number.
   - Calls `compute_diffs()` to find field-level differences (only for `MAPPED` columns).
   - Calls `classify_diffs_deterministically()` to resolve obvious cases without LLM:
     - One side is empty → `real_mismatch`.
     - Alphanumeric-stripped values are equal → `acceptable_variation`.
     - Anything else → passed to the agent.
   - Calls `ValidationAgent.classify()` for remaining ambiguous diffs.
   - Assembles `ValidationResult` per student.

2. **`write_validation_report(path, results)`** — one row per student with pass/fail indicator, counts, and review reason.

3. **`write_mismatch_report(path, results)`** — one row per `real_mismatch` field across all students, with Master value, Company value, classification, and confidence.

---

### Repositories

Repositories manage data access patterns. They sit between services (which do I/O) and nodes (which orchestrate).

#### `app/repositories/master_repository.py` — `MasterRepository`

Singleton. Wraps `excel_service.load_master_database()` and builds three in-memory hash-map indices after loading:
- `_by_enrollment` — `{normalized_enrollment → MasterRecord}` (unique).
- `_by_phone` — `{normalized_phone → list[MasterRecord]}` (may have duplicates).
- `_by_email` — `{normalized_email → list[MasterRecord]}` (may have duplicates).

`get_by_enrollment()`, `get_by_phone()`, `get_by_email()` enable O(1) lookups for the identity hierarchy. Raises `MasterRepositoryError` if accessed before `load()` is called.

#### `app/repositories/company_repository.py` — `CompanyRepository`

Created fresh per run (via `new_company_repository()` factory — not a singleton). Holds the in-progress Company Database for one run. Three enrichment phases:

1. `initialize(run_id, headers, raw_rows)` — stores raw rows by index.
2. `populate_from_master(master_records, column_mappings)` — creates one `CompanyRecord` per student, filling each company column from the corresponding Master DB field via the mappings.
3. `merge_form_responses(responses, missing_fields)` — fills in `missing_field_values` from Google Form responses, keyed by enrollment number.
4. `attach_resume_data(resume_data)` — links a resolved resume identity to the matching record.

`to_output_rows(mappings)` exports all records as plain dicts ready for the Excel Service to write.

#### `app/repositories/vector_repository.py` — `VectorRepository`

Singleton. Manages the `master_db_fields` ChromaDB collection lifecycle. `index_master_fields()` upserts all 17 `MASTER_DB_FIELDS` entries (field name + description as document text) into ChromaDB using the Embedding Service. Safe to call multiple times — skips re-indexing if the count already matches. `query_similar_fields(text, top_k)` delegates to `vector_service.query_similar()`.

#### `app/repositories/collection_repository.py` — `CollectionRepository`

Per-run (not singleton). Wraps `google_service.get_form_responses()` and normalizes the raw Sheet rows: maps common header variations (`enroll_no`, `reg_no`, `student_name`, etc.) to canonical field names. `get_pending_enrollments(all_enrollments)` returns students who haven't responded yet.

---

### AI Agents

Agents are where the LLM is actually invoked. Each uses `llm_service.generate_structured()` with a Pydantic output schema. All are singletons.

#### `app/agents/schema_agent.py` — `SchemaAgent`

**Purpose:** Map each company column header to a canonical Master DB field name.

**Two-stage process per column:**
1. **Embedding search** — calls `vector_repository.query_similar_fields(column_name + sample_values, top_k=5)` to retrieve the 5 most semantically similar Master DB fields.
2. **LLM reasoning** — sends the column name, sample cell values, and the 5 candidate fields to the LLM. The LLM returns a `_ColumnMappingOutput` (matched field, inferred type, confidence, reason). This prevents the LLM from hallucinating field names not in the Master DB.

**Result:** `MAPPED` if `confidence >= COLUMN_MAPPING_CONFIDENCE_THRESHOLD`, `NEEDS_REVIEW` if below, `MISSING_FIELD` if LLM returns `null`.

`low_confidence_fraction(mappings)` — returns the fraction of non-skipped mappings that are `NEEDS_REVIEW`. Used by `nodes.py` to decide whether to retry or escalate.

#### `app/agents/resume_extract_identity_agent.py` — `ResumeExtractIdentityAgent`

**Purpose:** AI fallback when the deterministic enrollment→phone→email chain fails.

**Input:** partial resume data (raw text), form-declared identity (enrollment + name from form response), and a shortlist of candidate Master records.

**Process:** Sends the first 3000 chars of resume text + form-declared identity + up to 10 candidates to the LLM. The LLM returns an enrollment number + confidence.

**Confidence gate:** If `confidence < IDENTITY_CONFIDENCE_THRESHOLD` → sets `needs_human_review=True` instead of auto-accepting. Conservative by design: false positives (flagging a correct match) are far less harmful than false negatives (auto-accepting a wrong identity).

#### `app/agents/validation_agent.py` — `ValidationAgent`

**Purpose:** Classify ambiguous field-level diffs that deterministic logic couldn't resolve.

**Batched:** All ambiguous diffs for one student are sent in a single prompt (not one call per diff). The LLM returns a `_ValidationAgentOutput` with a `classifications` array, one entry per diff in the same order.

**Conservative defaults:**
- If the LLM fails entirely → all diffs default to `real_mismatch`.
- If the LLM returns fewer items than expected → missing entries are padded with `real_mismatch`.
- If the LLM returns an unrecognized classification label → defaults to `real_mismatch`.

#### `app/agents/reminder_agent.py` — `ReminderAgent`

**Purpose:** Draft a friendly WhatsApp reminder message for students who haven't filled the form.

**Lowest stakes agent** — only generates human-facing text, makes no data decisions. Uses a higher temperature (`LLM_REMINDER_TEMPERATURE`) for more natural language.

**Full static fallback:** If the LLM call fails for any reason, uses a hardcoded template with `{form_url}`, `{company_name}`, `{deadline}`, and `{pending_count}` substituted. The pipeline never blocks on this agent.

---

### LangGraph Pipeline

#### `app/graph/state.py` — `PipelineState`

A `TypedDict` (total=False, so all fields are optional at creation). This is the single object threaded through every pipeline node. Contains:
- **Run metadata:** `run_id`, `company_name`, `submission_deadline`.
- **Inputs:** file paths, master records, company headers, sample rows.
- **Schema:** `column_mappings`, `schema_mapping_attempts`, `schema_needs_review`.
- **Population:** `missing_fields`.
- **Forms:** `google_form_id`, `google_form_url`, `whatsapp_message`, `form_responses`.
- **Resumes:** `resume_files`, `resolved_identities`, `identity_resolution_attempts`.
- **Validation:** `validation_results`.
- **Outputs:** three output file paths.
- **Control:** `status`, `current_node`, `errors`.

No node communicates with another through anything other than this state. This ensures `run_state.json` is always a complete, replayable snapshot.

#### `app/graph/nodes.py` — 16 Node Functions

Each node receives `PipelineState`, does its work by calling services/repositories/agents, and returns a **partial dict** (only the keys it changed). LangGraph merges this into the full state. Nodes never raise — they catch exceptions and add to `state["errors"]` instead.

| Node | What it does |
|---|---|
| `load_master` | Calls `master_repository.load(file_path)`, writes `master_records` to state |
| `ingest_company_upload` | Calls `excel_service.parse_company_upload()`, writes `company_headers` + `company_sample_rows` |
| `run_schema_agent` | Calls `schema_agent.run()`, writes `column_mappings` + `schema_mapping_attempts` |
| `retry_schema_agent` | Re-runs Schema Agent on only `NEEDS_REVIEW` columns; merges with existing confident mappings |
| `populate_company_db` | Creates `CompanyRepository`, calls `populate_from_master()`, stores repo in `_company_repositories[run_id]` |
| `detect_missing_fields` | Collects all `MISSING_FIELD` mappings into `state["missing_fields"]` |
| `generate_google_form` | Calls `google_service.create_form()`, writes form ID + URL |
| `generate_whatsapp_message` | Calls `reminder_agent.draft_message()` + `whatsapp_service.format_message()` |
| `await_responses` | Calls `google_service.get_form_responses()`, writes `form_responses` |
| `parse_resumes` | Calls `pdf_service.parse_resume()` for each file, stores in `_parsed_resumes` |
| `deterministic_identity_match` | Calls `run_deterministic_match()` per resume; splits into `resolved_identities` + `_needs_ai_resolution` |
| `run_resume_identity_agent` | Calls `resume_extract_identity_agent.resolve()` for unmatched resumes |
| `merge_form_and_resume_data` | Calls `repo.merge_form_responses()` + `repo.attach_resume_data()` |
| `run_validation` | Calls `report_service.build_validation_results()` |
| `generate_reports` | Calls Excel Service + Report Service to write the 3 output files; sets `status=completed` |
| `human_review_gate` | Terminal node — sets `status=awaiting_human_review`; run resumes via POST `/runs/{id}/resume` |

#### `app/graph/edges.py` — 5 Conditional Routing Functions

Each function receives the current state and returns the name of the next node. These are the branch decisions:

| Function | Decision |
|---|---|
| `after_run_schema_agent` | Low confidence fraction > threshold **and** attempts < max_retries → `retry_schema_agent`. Exhausted retries → `human_review_gate`. Otherwise → `populate_company_db`. |
| `after_detect_missing_fields` | Missing fields exist → `generate_google_form`. None missing → skip to `run_validation`. |
| `after_await_responses` | Responses received → `parse_resumes`. No responses (stub/timeout) → `run_validation` (avoids infinite loop in MVP). |
| `after_deterministic_identity_match` | Any unresolved resumes → `run_resume_identity_agent`. All resolved → `merge_form_and_resume_data`. |
| `after_run_resume_identity_agent` | Any `needs_human_review` or `resolution_failed` → `human_review_gate`. All resolved → `merge_form_and_resume_data`. |

#### `app/graph/pipeline_graph.py` — Compiled Graph

Instantiates a `StateGraph(PipelineState)`, registers all 16 nodes, sets `load_master` as the entry point, adds all edges (linear + conditional), and calls `graph.compile()`. Exports `pipeline_graph` singleton. This is the object that `process_routes.py` calls with `.invoke(initial_state)`.

---

### Storage

#### `app/storage/file_storage.py` — `FileStorage`

Manages all filesystem layout. Provides:
- `init_run(run_id)` — creates `data/runs/{run_id}/uploads/` and `outputs/`.
- `save_upload(run_id, filename, bytes)` — writes a file to `uploads/`.
- `save_state(run_id, state_dict)` — serializes the LangGraph state to `run_state.json` (handles Pydantic models, Path objects, enums via `_make_serializable()`).
- `load_state(run_id)` — reads and returns the last saved state dict.
- `get_outputs_dir(run_id)` — used by `generate_reports` node to know where to write files.

`data/` is entirely gitignored. The `data/master/` directory is where the coordinator places the Master Database file.

---

### API Layer

#### `app/api/schemas/requests.py`

Pydantic request models for every endpoint:
- `LoadMasterRequest` — file path (defaults to `data/master/master_database.xlsx`).
- `ProcessRequest` — company name, deadline, company file path.
- `PopulateRequest` / `ValidateRequest` — just a `run_id`.
- `CorrectionItem` — type + column/field/resume/master_record identifiers for human corrections.
- `ResumeRunRequest` — list of `CorrectionItem`.

#### `app/api/schemas/responses.py`

Matching response models: `LoadMasterResponse`, `ProcessResponse`, `PopulateResponse`, `FormStatusResponse`, `ValidateResponse`, `ReportResponse`, `ResumeRunResponse`, `HealthResponse`.

#### `app/api/routes/master_routes.py`

`POST /master/load` — calls `master_repository.load(request.file_path)`, returns record count.

#### `app/api/routes/form_routes.py`

- `POST /forms/upload` — generates a new `run_id`, saves the uploaded file via `file_storage.save_upload()`, returns `run_id` + saved path. This is typically the **first API call** a coordinator makes.
- `GET /forms/{run_id}` — reads `google_form_url` and `whatsapp_message` from `_run_states`.

#### `app/api/routes/process_routes.py`

- `POST /process` — validates that Master DB is loaded, creates initial `PipelineState`, adds `_run_pipeline()` as a background task (runs in a thread pool executor), returns `run_id` immediately.
- `GET /process/{run_id}/status` — reads from `_run_states` dict (in-memory).

`_run_states` is currently in-memory (lost on server restart). The compiled state is also saved to `run_state.json` via `file_storage.save_state()` for debugging.

#### `app/api/routes/populate_routes.py`

`POST /populate` — runs schema mapping only, without starting the full pipeline. Useful to preview column mappings before committing to a run.

#### `app/api/routes/validate_routes.py`

`POST /validate` — re-runs `report_service.build_validation_results()` against the in-memory company repository. Used after a coordinator provides corrections at `human_review_gate`.

#### `app/api/routes/report_routes.py`

- `GET /reports/{run_id}` — returns all three output file paths from state.
- `GET /reports/{run_id}/download?report_type=...` — serves the file as a `FileResponse` download. `report_type` is one of `populated_database`, `validation_report`, `mismatch_report`.
- `POST /runs/{run_id}/resume` — applies `CorrectionItem` list to column mappings and identity resolutions in state, sets status back to `running`.

---

## Data Flow Diagram (Simplified)

```
.env ──────────────────────────────────────────────────────────────────►
                                                                config.py
                                                                    │
                                                         ┌──────────▼──────────┐
              master_database.xlsx ──► ExcelService ──► MasterRepository (indices)
                                                                    │
              company_upload.xlsx ──► ExcelService ─────────────────┤
                                     (headers + 5 rows)             │
                                              │                     │
                                              ▼                     │
                                       SchemaAgent ◄── VectorRepository ◄── ChromaDB
                                       (+ LLMService)               │
                                              │ ColumnMappings      │
                                              ▼                     ▼
                                       CompanyRepository.populate_from_master()
                                              │
                                    ┌─────────┴──────────┐
                            missing fields?           all fields present
                                    │                       │
                                    ▼                       │
                            GoogleService (form)            │
                            ReminderAgent (msg)             │
                                    │                       │
                            form responses arrive           │
                                    │                       │
                            PDFService (parse resumes)      │
                                    │                       │
                            identity_hierarchy              │
                              (deterministic)               │
                                    │ failed?               │
                                    ▼                       │
                            ResumeExtractIdentityAgent      │
                            (+ LLMService)                  │
                                    │                       │
                                    └──────────┬────────────┘
                                               ▼
                                    CompanyRepository.merge()
                                               │
                                               ▼
                              ReportService.build_validation_results()
                                    │
                          ┌─────────┤
                          │         ▼
                          │    ValidationAgent (ambiguous diffs)
                          │    (+ LLMService)
                          │         │
                          └─────────┘
                                    ▼
                          ExcelService + ReportService
                          write 3 output Excel files
```

---

## Typical API Call Sequence

```bash
# 1. Load the Master Database (once per session, or on change)
curl -X POST http://localhost:8000/api/v1/master/load \
  -H "Content-Type: application/json" \
  -d '{"file_path": "data/master/master_database.xlsx"}'

# 2. Upload company Excel template
curl -X POST http://localhost:8000/api/v1/forms/upload \
  -F "file=@/path/to/company_template.xlsx"
# → {"run_id": "r_abc123", "file_path": "data/runs/r_abc123/uploads/..."}

# 3. Start the pipeline
curl -X POST http://localhost:8000/api/v1/process \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "Acme Corp",
    "submission_deadline": "2026-08-15T18:00:00Z",
    "company_file_path": "data/runs/r_abc123/uploads/company_template.xlsx"
  }'
# → {"run_id": "r_abc123", "status": "running"}

# 4. Poll for completion
curl http://localhost:8000/api/v1/process/r_abc123/status

# 5. Download the populated database
curl "http://localhost:8000/api/v1/reports/r_abc123/download?report_type=populated_database" \
  -o populated_database.xlsx
```

---

## Gotchas & Known Limitations

- **Ollama must be running** before schema mapping or any AI agent is used. The server starts fine without it, but pipeline runs will fail at `run_schema_agent`. Configure `OLLAMA_BASE_URL` in `.env`.
- **Pull both models** before first use: `ollama pull llama3.1 && ollama pull nomic-embed-text`.
- **Master DB must be loaded first.** `POST /process` will return HTTP 400 if `POST /master/load` has not been called in the current session. The master DB is in-memory only and does not survive server restarts.
- **`_run_states` is in-memory.** Pipeline status is lost on server restart. The `run_state.json` file persists to disk for each run but is not automatically re-loaded into the in-memory dict. For production, back `_run_states` with a database or `file_storage.load_state()`.
- **Enrollment number regex** in `constants.py` is institution-specific. Pattern `\b\d{2}[A-Z]{2,4}\d{2,4}\b` matches formats like `21CS045`. Adjust if your format differs.
- **Google integration is stubbed.** `create_form()` returns a fake URL; `get_form_responses()` returns `[]`. Enable with `GOOGLE_INTEGRATION_ENABLED=true` + service account credentials.
- **Resume downloading is stubbed.** In the current MVP, `resume_files` in the pipeline state is always empty unless you manually populate it before calling `POST /process`.
- **`POST /runs/{run_id}/resume`** applies corrections to in-memory state but does not yet re-invoke the LangGraph from `merge_form_and_resume_data`. After resuming, manually call `POST /validate` to re-run validation with the corrected data.


3. Ollama Setup Guide for README.md
Here is a clean Markdown section you can copy and paste directly into your project's README.md:

Markdown
## Ollama & Model Setup Guide

This project relies on [Ollama](https://ollama.com/) for local LLM inference (`llama3.2`) and text embeddings (`nomic-embed-text`).

### 1. Install Ollama
* **Windows / macOS:** Download and run the installer from [ollama.com/download](https://ollama.com/download).
* **Linux:** Run the installation script:
  ```bash
  curl -fsSL [https://ollama.com/install.sh](https://ollama.com/install.sh) | sh
2. Verify Ollama Service is Running
Ollama runs as a background service by default on port 11434. You can verify it's running by opening your terminal or browser:

Bash
curl http://localhost:11434
# Should return: "Ollama is running"
3. Pull Required Models
Open your terminal/PowerShell and pull both the chat model and the embedding model required by tnp_backend:

Bash
# Pull the LLM model
ollama pull llama3.2

# Pull the text embedding model
ollama pull nomic-embed-text
4. Project Configuration
Ensure your .env file in tnp_backend reflects your local Ollama instance:

Code snippet
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
EMBEDDING_MODEL=nomic-embed-text
Once the models are pulled, restart your FastAPI backend server:

PowerShell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload