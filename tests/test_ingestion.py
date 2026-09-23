import io

import pytest
from docx import Document

from core.config import Settings
from core.ingestion import ResumeIngestionError, parse_resume_bytes


def test_parses_utf8_text_resume():
    document = parse_resume_bytes(b"Jane Doe\nPython developer", "resume.txt")
    assert document.name == "resume.txt"
    assert document.text.endswith("Python developer")
    assert "Jane Doe" not in document.redacted_text


def test_parses_docx_resume():
    source = Document()
    source.add_paragraph("Alex Example")
    source.add_paragraph("Built FastAPI services")
    buffer = io.BytesIO()
    source.save(buffer)
    result = parse_resume_bytes(buffer.getvalue(), "resume.docx")
    assert "Built FastAPI services" in result.text


def test_rejects_unsupported_extension():
    with pytest.raises(ResumeIngestionError, match="Unsupported"):
        parse_resume_bytes(b"hello", "resume.rtf")


def test_rejects_oversize_file(tmp_path):
    settings = Settings(data_dir=tmp_path, max_file_bytes=3)
    with pytest.raises(ResumeIngestionError, match="5 MB"):
        parse_resume_bytes(b"four", "resume.txt", settings)
