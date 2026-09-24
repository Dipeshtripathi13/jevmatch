from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    typesafe_api_key: str | None = None
    anthropic_api_key: str | None = None
    jev_model: str = "jev-1.13.0"
    anthropic_model: str = "claude-sonnet-4-5-20250929"
    data_dir: Path = Path("data")

    max_file_bytes: int = 5 * 1024 * 1024
    max_request_bytes: int = 25 * 1024 * 1024
    max_resume_text_chars: int = 200_000
    max_resumes_per_match: int = Field(default=25, ge=1, le=1_000)
    max_requirements_per_match: int = Field(default=50, ge=1, le=200)
    max_pdf_pages: int = Field(default=50, ge=1, le=1_000)
    max_docx_members: int = Field(default=1_000, ge=1, le=10_000)
    max_docx_uncompressed_bytes: int = 25 * 1024 * 1024
    max_docx_compression_ratio: float = Field(default=100.0, ge=1, le=10_000)
    max_jd_bytes: int = 2 * 1024 * 1024
    min_jd_chars: int = 300
    fetch_timeout_seconds: float = 15.0
    max_questions_per_call: int = 60
    max_concurrent_resumes: int = Field(default=3, ge=1, le=20)

    missing_must_have_threshold: float = 0.35
    uncertain_must_have_threshold: float = 0.65
    low_confidence_threshold: float = 0.55
    resume_probability_threshold: float = 0.5
    prompt_injection_threshold: float = Field(default=0.35, ge=0, le=1)
    must_have_score_cap: float = 50.0
    strong_match_threshold: float = 80.0
    partial_match_threshold: float = 55.0
    evidence_presence_threshold: float = Field(default=0.35, ge=0, le=1)
    evidence_threshold: float = 0.6
    evidence_limit: int = 3
    evidence_candidate_limit: int = Field(default=8, ge=1, le=20)
    evidence_window_lines: int = Field(default=200, ge=2, le=255)
    max_evidence_lines: int = Field(default=400, ge=1, le=5_000)

    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3_600)
    rate_limit_max_clients: int = Field(default=10_000, ge=100, le=1_000_000)
    match_rate_limit_per_window: int = Field(default=10, ge=1)
    upload_rate_limit_per_window: int = Field(default=30, ge=1)
    extraction_rate_limit_per_window: int = Field(default=10, ge=1)
    default_rate_limit_per_window: int = Field(default=120, ge=1)

    @property
    def database_path(self) -> Path:
        return self.data_dir / "jevmatch.db"

    @property
    def resumes_dir(self) -> Path:
        return self.data_dir / "resumes"


@lru_cache
def get_settings() -> Settings:
    return Settings()
