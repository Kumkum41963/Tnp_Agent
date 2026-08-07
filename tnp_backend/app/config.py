# Loads all .env variables providing default and type casting for other files to use
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Ollama ──────────────────────────────────────────────────────────────
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL of the Ollama server. Set to your external Ollama instance.",
    )
    ollama_model: str = Field(
        default="llama3.1",
        description="Chat model served by Ollama (e.g. llama3.1, mistral, gemma2).",
    )
    ollama_embedding_model: str = Field(
        default="nomic-embed-text",
        description="Embedding model served by Ollama. Pull with: ollama pull nomic-embed-text",
    )

    # ── LLM inference ───────────────────────────────────────────────────────
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    llm_reminder_temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=2048, ge=64)
    llm_timeout_seconds: int = Field(default=60, ge=5)

    # ── Pipeline thresholds ─────────────────────────────────────────────────
    column_mapping_confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    identity_confidence_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    schema_agent_low_confidence_fraction: float = Field(default=0.3, ge=0.0, le=1.0)
    schema_agent_max_retries: int = Field(default=2, ge=0)

    # ── Storage ─────────────────────────────────────────────────────────────
    data_dir: Path = Field(default=Path("./data"))
    chroma_persist_dir: Path = Field(default=Path("./app/storage/chroma_store"))

    # ── Google APIs ─────────────────────────────────────────────────────────
    google_integration_enabled: bool = Field(default=True)
    google_service_account_file: Path = Field(
        default=Path("C:/Users/kumku/OneDrive/Desktop/CODING/Projects/Tnp_Auto_Agent/tnp_backend/tnp-automation-5ea09ac2205d.json")
    )
    google_oauth_client_file: Path = Field(
        default=Path("C:/Users/kumku/OneDrive/Desktop/CODING/Projects/Tnp_Auto_Agent/tnp_backend/oauth_client.json")
    )
    google_oauth_token_file: Path = Field(
        default=Path("C:/Users/kumku/OneDrive/Desktop/CODING/Projects/Tnp_Auto_Agent/tnp_backend/token.json")
    )
    google_drive_folder_id: str = Field(default="")

    # ── API server ──────────────────────────────────────────────────────────
    port: int = Field(default=8000)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    @field_validator("data_dir", "chroma_persist_dir", mode="before")
    @classmethod
    def ensure_path(cls, v: object) -> Path:
        return Path(str(v))


# Singleton — import this everywhere
settings = Settings()
