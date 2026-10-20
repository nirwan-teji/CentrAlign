"""
core/config.py — Centralised application settings loaded from .env
Uses pydantic-settings for type-safe, validated configuration.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration values, sourced from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM ────────────────────────────────────────────────────────────────
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    primary_model: str = Field(default="openai/gpt-oss-120b", alias="PRIMARY_MODEL")
    fallback_model: str = Field(default="llama-3.3-70b-versatile", alias="FALLBACK_MODEL")
    fast_model: str = Field(default="llama-3.1-8b-instant", alias="FAST_MODEL")

    # ── Agent runtime ───────────────────────────────────────────────────────
    max_steps: int = Field(default=30, alias="MAX_STEPS")
    step_timeout_seconds: int = Field(default=60, alias="STEP_TIMEOUT_SECONDS")
    hitl_amount_threshold: float = Field(default=5000.0, alias="HITL_AMOUNT_THRESHOLD")

    # ── Sandbox ERP ─────────────────────────────────────────────────────────
    sandbox_erp_port: int = Field(default=8001, alias="SANDBOX_ERP_PORT")
    sandbox_erp_host: str = Field(default="localhost", alias="SANDBOX_ERP_HOST")
    sandbox_erp_hostport: Optional[str] = Field(default=None, alias="SANDBOX_ERP_HOSTPORT")
    sandbox_erp_username: str = Field(default="admin", alias="SANDBOX_ERP_USERNAME")
    sandbox_erp_password: str = Field(default="admin123", alias="SANDBOX_ERP_PASSWORD")

    # ── Agent server ────────────────────────────────────────────────────────
    agent_server_port: int = Field(default=8000, alias="AGENT_SERVER_PORT")
    agent_server_host: str = Field(default="localhost", alias="AGENT_SERVER_HOST")

    # ── Memory & storage ────────────────────────────────────────────────────
    chroma_db_path: str = Field(default="./data/chromadb", alias="CHROMA_DB_PATH")
    memory_collection: str = Field(default="centralign_memory", alias="MEMORY_COLLECTION")
    embedding_model: str = Field(default="all-MiniLM-L6-v2", alias="EMBEDDING_MODEL")

    # ── Logging & evidence ──────────────────────────────────────────────────
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    screenshots_dir: str = Field(default="./data/screenshots", alias="SCREENSHOTS_DIR")
    evidence_dir: str = Field(default="./data/evidence", alias="EVIDENCE_DIR")

    @field_validator("groq_api_key")
    @classmethod
    def warn_if_empty(cls, v: str) -> str:
        if not v or v == "your_groq_api_key_here":
            import warnings
            warnings.warn(
                "GROQ_API_KEY is not set. Set it in your .env file to use the LLM.",
                stacklevel=2,
            )
        return v

    @property
    def sandbox_erp_url(self) -> str:
        if self.sandbox_erp_hostport:
            return f"http://{self.sandbox_erp_hostport}"
        return f"http://{self.sandbox_erp_host}:{self.sandbox_erp_port}"

    @property
    def agent_server_url(self) -> str:
        return f"http://{self.agent_server_host}:{self.agent_server_port}"

    def ensure_dirs(self) -> None:
        """Create required data directories if they don't exist."""
        for path in [self.screenshots_dir, self.evidence_dir, self.chroma_db_path]:
            Path(path).mkdir(parents=True, exist_ok=True)


# Module-level singleton — import this everywhere
settings = Settings()
settings.ensure_dirs()
