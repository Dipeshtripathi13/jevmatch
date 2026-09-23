import io
from pathlib import Path

import pdfplumber
from docx import Document

from core.config import Settings, get_settings
from core.models import ResumeDocument
from core.redaction import redact_pii


class ResumeIngestionError(ValueError):
    pass


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def _parse_pdf(content: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as exc:
        raise ResumeIngestionError(f"Could not read PDF: {exc}") from exc
    if not text.strip():
        raise ResumeIngestionError(
            "This PDF has no extractable text and likely needs OCR before it can be scored."
        )
    return text


def _parse_docx(content: bytes) -> str:
    try:
        document = Document(io.BytesIO(content))
        paragraphs = [paragraph.text for paragraph in document.paragraphs]
        table_cells = [
            cell.text for table in document.tables for row in table.rows for cell in row.cells
        ]
        return "\n".join([*paragraphs, *table_cells])
    except Exception as exc:
        raise ResumeIngestionError(f"Could not read DOCX: {exc}") from exc


def parse_resume_bytes(
    content: bytes, filename: str, settings: Settings | None = None
) -> ResumeDocument:
    settings = settings or get_settings()
    if len(content) > settings.max_file_bytes:
        raise ResumeIngestionError("Resume exceeds the 5 MB file-size limit.")
    if not content:
        raise ResumeIngestionError("Resume file is empty.")

    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ResumeIngestionError("Unsupported resume type. Use PDF, DOCX, or TXT.")
    if suffix == ".pdf":
        text = _parse_pdf(content)
    elif suffix == ".docx":
        text = _parse_docx(content)
    else:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ResumeIngestionError("TXT resumes must use UTF-8 encoding.") from exc

    if not text.strip():
        raise ResumeIngestionError("Resume contains no readable text.")
    return ResumeDocument(
        name=Path(filename).name,
        text=text.strip(),
        redacted_text=redact_pii(text.strip()),
        size_bytes=len(content),
    )


def parse_resume_file(path: Path | str, settings: Settings | None = None) -> ResumeDocument:
    path = Path(path)
    if not path.is_file():
        raise ResumeIngestionError(f"Resume not found: {path}")
    document = parse_resume_bytes(path.read_bytes(), path.name, settings)
    document.source_path = str(path)
    return document
