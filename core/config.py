from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    typesafe_api_key: str | None = None
    anthropic_api_key: str | None = None
    jev_model: str = "jev-1.13.0"
    anthropic_model: str = "claude-sonnet-4-5-20250929"
    data_dir: Path = Path("data")

    max_file_bytes: int = 5 * 1024 * 1024
    max_jd_bytes: int = 2 * 1024 * 1024
    min_jd_chars: int = 300
    fetch_timeout_seconds: float = 15.0
    max_questions_per_call: int = 60

    missing_must_have_threshold: float = 0.35
    uncertain_must_have_threshold: float = 0.65
    low_confidence_threshold: float = 0.55
    resume_probability_threshold: float = 0.5
    must_have_score_cap: float = 50.0
    strong_match_threshold: float = 80.0
    partial_match_threshold: float = 55.0
    evidence_threshold: float = 0.6
    evidence_limit: int = 3

    @property
    def database_path(self) -> Path:
        return self.data_dir / "jevmatch.db"

    @property
    def resumes_dir(self) -> Path:
        return self.data_dir / "resumes"


@lru_cache
def get_settings() -> Settings:
    return Settings()
