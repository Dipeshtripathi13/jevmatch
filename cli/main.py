import asyncio
import csv
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from core.config import get_settings
from core.ingestion import SUPPORTED_EXTENSIONS, parse_resume_file
from core.jd import fetch_jd_url, read_jd_file
from core.models import ExtractedRequirements, MatchResult
from core.pipeline import MatchPipeline
from core.requirements import RequirementExtractor
from core.storage import (
    import_saved_resume,
    init_db,
    list_saved_resumes,
    load_saved_resume,
    remove_saved_resume,
)

app = typer.Typer(help="Score resume-to-job fit with TypeSafe Jev.", no_args_is_help=True)
library_app = typer.Typer(help="Manage the local resume library.")
jd_app = typer.Typer(help="Fetch and inspect job descriptions.")
app.add_typer(library_app, name="library")
app.add_typer(jd_app, name="jd")
console = Console()


def _fail(message: str, code: int = 1) -> None:
    console.print(f"[bold red]Error:[/] {message}", stderr=True)
    raise typer.Exit(code)


async def _job_text(url: str | None, file: Path | None, text: str | None) -> str:
    supplied = sum(value is not None for value in (url, file, text))
    if supplied != 1:
        _fail("Provide exactly one of --jd-url, --jd-file, or --jd-text.")
    if url:
        return await fetch_jd_url(url)
    if file:
        return read_jd_file(file)
    return (text or "").strip()


def _edit_requirements(extracted: ExtractedRequirements) -> ExtractedRequirements:
    editor = os.environ.get("EDITOR")
    if not editor:
        _fail("--edit-requirements needs the EDITOR environment variable.")
    with tempfile.NamedTemporaryFile(
        suffix=".json", mode="w+", encoding="utf-8", delete=False
    ) as handle:
        path = Path(handle.name)
        handle.write(extracted.model_dump_json(indent=2))
    try:
        command = [*shlex.split(editor), str(path)]
        if subprocess.run(command, check=False).returncode != 0:
            _fail("The editor exited with an error.")
        return ExtractedRequirements.model_validate_json(path.read_text(encoding="utf-8"))
    finally:
        path.unlink(missing_ok=True)


def _render_results(results: list[MatchResult], verbose: bool = False) -> None:
    table = Table(title="JevMatch ranking", show_lines=False)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Resume")
    table.add_column("Score", justify="right")
    table.add_column("Verdict")
    table.add_column("Review")
    for index, result in enumerate(results, 1):
        color = (
            "green" if result.match_score >= 80 else "yellow" if result.match_score >= 55 else "red"
        )
        table.add_row(
            str(index),
            result.resume_name,
            f"[{color}]{result.match_score:.1f}[/]",
            result.verdict.replace("_", " "),
            "yes" if result.requires_human_review else "no",
        )
    console.print(table)
    if len(results) == 1:
        result = results[0]
        details = Table(title="Requirement evidence")
        details.add_column("Requirement")
        details.add_column("Result", justify="right")
        details.add_column("Confidence", justify="right")
        details.add_column("Top evidence")
        for item in result.requirement_results:
            details.add_row(
                item.requirement.text,
                f"{item.normalized_score * 100:.0f}%",
                f"{item.confidence:.2f}" if item.confidence is not None else "—",
                "\n".join(item.evidence) or "—",
            )
        console.print(details)
    if verbose:
        console.print_json(json.dumps([result.raw_jev_answers for result in results]))


def _write_csv(path: Path, results: list[MatchResult]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["rank", "resume", "score", "verdict", "human_review", "missing_must_haves"],
        )
        writer.writeheader()
        for rank, result in enumerate(results, 1):
            writer.writerow(
                {
                    "rank": rank,
                    "resume": result.resume_name,
                    "score": result.match_score,
                    "verdict": result.verdict,
                    "human_review": result.requires_human_review,
                    "missing_must_haves": "; ".join(result.missing_must_haves),
                }
            )


@app.command()
def match(
    resume: Annotated[
        list[Path] | None, typer.Option("--resume", help="Resume file; repeatable.")
    ] = None,
    resume_dir: Annotated[Path | None, typer.Option("--resume-dir")] = None,
    saved: Annotated[
        list[str] | None, typer.Option("--saved", help="Saved resume ID; repeatable.")
    ] = None,
    jd_url: Annotated[str | None, typer.Option("--jd-url")] = None,
    jd_file: Annotated[Path | None, typer.Option("--jd-file")] = None,
    jd_text: Annotated[str | None, typer.Option("--jd-text")] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON.")
    ] = False,
    csv_path: Annotated[Path | None, typer.Option("--csv", help="Write ranked CSV output.")] = None,
    model: Annotated[str, typer.Option("--model")] = "jev-1.13.0",
    edit_requirements: Annotated[bool, typer.Option("--edit-requirements")] = False,
    verbose: Annotated[bool, typer.Option("--verbose")] = False,
    evidence: Annotated[bool, typer.Option("--evidence/--no-evidence")] = True,
) -> None:
    """Score one or many resumes against a job description."""

    async def run() -> list[MatchResult]:
        settings = get_settings()
        settings.jev_model = model
        documents = []
        for path in resume or []:
            documents.append((None, parse_resume_file(path, settings)))
        if resume_dir:
            if not resume_dir.is_dir():
                _fail(f"Resume directory not found: {resume_dir}")
            for path in sorted(resume_dir.iterdir()):
                if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    documents.append((None, parse_resume_file(path, settings)))
        for resume_id in saved or []:
            documents.append((resume_id, load_saved_resume(resume_id, settings)))
        if not documents:
            _fail("Provide --resume, --resume-dir, or --saved.")
        text = await _job_text(jd_url, jd_file, jd_text)
        extracted = await RequirementExtractor(settings).extract(text)
        if edit_requirements:
            extracted = _edit_requirements(extracted)
        return await MatchPipeline(settings).match_many(
            documents, extracted, include_evidence=evidence
        )

    try:
        with Progress(
            SpinnerColumn(), TextColumn("{task.description}"), console=console, transient=True
        ) as progress:
            progress.add_task("Evaluating resumes…", total=None)
            results = asyncio.run(run())
    except typer.Exit:
        raise
    except (OSError, ValueError, KeyError) as exc:
        _fail(str(exc), 1)
    except Exception as exc:
        _fail(str(exc), 2)
    if json_output:
        console.print_json(json.dumps([result.model_dump(mode="json") for result in results]))
    else:
        _render_results(results, verbose)
    if csv_path:
        _write_csv(csv_path, results)
        console.print(f"Wrote [cyan]{csv_path}[/]")


@library_app.command("add")
def library_add(path: Path, name: Annotated[str | None, typer.Option("--name")] = None) -> None:
    """Copy a resume into the local library."""
    try:
        record = import_saved_resume(path, name)
        console.print(f"Added [bold]{record.name}[/] as [cyan]{record.id}[/]")
    except (OSError, ValueError) as exc:
        _fail(str(exc))


@library_app.command("list")
def library_list() -> None:
    """List locally saved resumes."""
    init_db()
    table = Table("ID", "Name", "Uploaded", "Size")
    for record in list_saved_resumes():
        table.add_row(
            record.id,
            record.name,
            record.created_at.isoformat(timespec="minutes"),
            f"{record.size_bytes:,} B",
        )
    console.print(table)


@library_app.command("remove")
def library_remove(resume_id: str) -> None:
    """Remove a resume and its local file."""
    try:
        remove_saved_resume(resume_id)
        console.print("Removed resume.")
    except KeyError as exc:
        _fail(str(exc))


@jd_app.command("show")
def jd_show(
    url: Annotated[str | None, typer.Option("--url")] = None,
    file: Annotated[Path | None, typer.Option("--file")] = None,
    text: Annotated[str | None, typer.Option("--text")] = None,
) -> None:
    """Preview extracted JD text and structured requirements."""

    async def run():
        job_text = await _job_text(url, file, text)
        return job_text, await RequirementExtractor().extract(job_text)

    try:
        job_text, extracted = asyncio.run(run())
    except Exception as exc:
        _fail(str(exc), 2)
    console.rule("Job description")
    console.print(job_text)
    console.rule("Requirements")
    console.print_json(extracted.model_dump_json())


if __name__ == "__main__":
    app()
