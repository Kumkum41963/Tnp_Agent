# TNP Automation Platform

An AI-powered backend platform designed to automate the Training & Placement (TNP) workflow by intelligently processing company requirements, generating Google Forms, collecting student responses, downloading resumes, and preparing structured datasets for recruiters.

The platform combines Large Language Models (LLMs), Google Workspace APIs, semantic document processing, and automated workflow orchestration to significantly reduce the manual effort involved in placement drives.

---

## Features

- AI-powered extraction of company hiring requirements
- Intelligent detection of missing student information
- Automatic Google Form generation
- OAuth-based Google Forms integration
- Google Drive integration for resume collection
- Automatic resume downloading and organization
- Semantic document processing using ChromaDB embeddings
- LLM-based schema understanding and column mapping
- Automated validation and data normalization
- Multi-stage LangGraph workflow orchestration
- Human review support for low-confidence mappings
- REST APIs built with FastAPI
- Modular service-oriented backend architecture

---

## Tech Stack

### Backend

- FastAPI
- Python 3.11+
- Pydantic
- LangGraph
- LangChain
- Ollama (Local LLM)
- ChromaDB

### Google Integrations

- Google Forms API
- Google Drive API
- OAuth 2.0
- Google Service Account

### AI & NLP

- Llama 3.1 (Ollama)
- Embedding Models
- Semantic Search
- Retrieval-Augmented Processing

### Data Processing

- Pandas
- NumPy
- OpenPyXL
- PyMuPDF

---

## Workflow

```text
Company Requirements
        │
        ▼
 Requirement Extraction (LLM)
        │
        ▼
 Missing Field Detection
        │
        ▼
 Google Form Generation
        │
        ▼
 Student Responses
        │
        ▼
 Resume Collection
        │
        ▼
 Resume Download
        │
        ▼
 Information Extraction
        │
        ▼
 Semantic Column Mapping
        │
        ▼
 Validation & Human Review
        │
        ▼
 Final Structured Dataset
```

---

## Architecture

```text
                FastAPI REST API
                        │
                        ▼
                 LangGraph Pipeline
                        │
 ┌───────────────┬───────────────┬────────────────┐
 │               │               │                │
 ▼               ▼               ▼                ▼
Google APIs   LLM Service   ChromaDB      Data Processing
 │               │               │                │
 ▼               ▼               ▼                ▼
Forms       Requirement     Embeddings      Excel/PDF
Drive        Extraction      Retrieval      Processing
```

---

## Project Structure

```
app/
│
├── api/
├── config/
├── graph/
├── repositories/
├── services/
├── storage/
├── models/
├── schemas/
├── utils/
└── main.py

credentials/
│
├── oauth_client.json
├── token.json
└── service_account.json

data/
tests/
```

---

## Current Capabilities

- Generate Google Forms dynamically from company requirements
- Collect structured student responses
- Download resumes from Google Drive links
- Automatically identify missing candidate information
- AI-assisted schema matching
- Confidence-based validation
- Human review pipeline
- End-to-end workflow automation

---

## Future Improvements

- Multi-user authentication and role management
- Branch-wise admin dashboard
- Student dashboard
- Placement analytics
- Email and WhatsApp notifications
- Kubernetes deployment
- CI/CD pipeline
- Observability using Prometheus and Grafana
- Vector database optimization
- Multi-model LLM support

---

## Security

- OAuth 2.0 authentication for Google Forms
- Service Account authentication for Google Drive
- Environment variable based configuration
- Secrets excluded from version control
- Modular API architecture

---

## Installation

```bash
git clone <repository>

cd tnp_backend

pip install -e .
```

Configure the required environment variables inside `.env` before running the application.

---

## Run

```bash
uvicorn app.main:app --reload
```

---

## API Documentation

After starting the server:

```
http://localhost:8000/docs
```

Swagger UI provides interactive API documentation for all available endpoints.

---

## License

This project is intended for educational, research, and academic placement automation purposes.
