import json
import shutil
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Column, Text
from sqlmodel import Field, Session, SQLModel, create_engine, select

from core.config import Settings, get_settings
from core.ingestion import parse_resume_bytes, parse_resume_file
from core.models import ExtractedRequirements, ResumeDocument


class SavedResume(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str = Field(index=True, max_length=255)
    filename: str = Field(max_length=255)
    stored_path: str = Field(unique=True)
    size_bytes: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RequirementCache(SQLModel, table=True):
    jd_hash: str = Field(primary_key=True)
    payload: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


@lru_cache
def _engine_for_path(database_path: str):
    return create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False})


def get_engine(settings: Settings | None = None):
    settings = settings or get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return _engine_for_path(str(settings.database_path.resolve()))


def init_db(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    settings.resumes_dir.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(get_engine(settings))


def add_saved_resume(
    content: bytes, filename: str, name: str | None = None, settings: Settings | None = None
) -> SavedResume:
    settings = settings or get_settings()
    init_db(settings)
    document = parse_resume_bytes(content, filename, settings)
    record_id = str(uuid.uuid4())
    suffix = Path(filename).suffix.lower()
    destination = settings.resumes_dir / f"{record_id}{suffix}"
    destination.write_bytes(content)
    record = SavedResume(
        id=record_id,
        name=(name or Path(filename).stem).strip(),
        filename=Path(filename).name,
        stored_path=str(destination.resolve()),
        size_bytes=document.size_bytes,
    )
    with Session(get_engine(settings)) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def import_saved_resume(
    source: Path | str, name: str | None = None, settings: Settings | None = None
) -> SavedResume:
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(path)
    return add_saved_resume(path.read_bytes(), path.name, name, settings)


def list_saved_resumes(settings: Settings | None = None) -> list[SavedResume]:
    settings = settings or get_settings()
    init_db(settings)
    with Session(get_engine(settings)) as session:
        return list(session.exec(select(SavedResume).order_by(SavedResume.created_at.desc())).all())


def get_saved_resume(resume_id: str, settings: Settings | None = None) -> SavedResume | None:
    settings = settings or get_settings()
    init_db(settings)
    with Session(get_engine(settings)) as session:
        return session.get(SavedResume, resume_id)


def load_saved_resume(resume_id: str, settings: Settings | None = None) -> ResumeDocument:
    settings = settings or get_settings()
    record = get_saved_resume(resume_id, settings)
    if not record:
        raise KeyError(f"Saved resume not found: {resume_id}")
    document = parse_resume_file(record.stored_path, settings)
    document.name = record.name
    return document


def rename_saved_resume(resume_id: str, name: str, settings: Settings | None = None) -> SavedResume:
    settings = settings or get_settings()
    init_db(settings)
    with Session(get_engine(settings)) as session:
        record = session.get(SavedResume, resume_id)
        if not record:
            raise KeyError(f"Saved resume not found: {resume_id}")
        record.name = name.strip()
        session.add(record)
        session.commit()
        session.refresh(record)
        return record


def remove_saved_resume(resume_id: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    init_db(settings)
    with Session(get_engine(settings)) as session:
        record = session.get(SavedResume, resume_id)
        if not record:
            raise KeyError(f"Saved resume not found: {resume_id}")
        stored_path = Path(record.stored_path)
        session.delete(record)
        session.commit()
    stored_path.unlink(missing_ok=True)


def clear_storage(settings: Settings) -> None:
    """Test helper for an isolated data directory."""
    _engine_for_path.cache_clear()
    if settings.data_dir.exists():
        shutil.rmtree(settings.data_dir)


def get_cached_requirements(
    jd_hash: str, settings: Settings | None = None
) -> ExtractedRequirements | None:
    settings = settings or get_settings()
    init_db(settings)
    with Session(get_engine(settings)) as session:
        cached = session.get(RequirementCache, jd_hash)
        return ExtractedRequirements.model_validate_json(cached.payload) if cached else None


def cache_requirements(
    jd_hash: str, requirements: ExtractedRequirements, settings: Settings | None = None
) -> None:
    settings = settings or get_settings()
    init_db(settings)
    payload = json.dumps(requirements.model_dump(mode="json"), separators=(",", ":"))
    with Session(get_engine(settings)) as session:
        existing = session.get(RequirementCache, jd_hash)
        if existing:
            existing.payload = payload
            existing.created_at = datetime.now(UTC)
            session.add(existing)
        else:
            session.add(RequirementCache(jd_hash=jd_hash, payload=payload))
        session.commit()
