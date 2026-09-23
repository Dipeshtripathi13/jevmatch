from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import (
    JDFetchRequest,
    JDTextResponse,
    MatchRequest,
    MatchResponse,
    RenameResumeRequest,
    RequirementRequest,
    ResumeResponse,
)
from core.config import get_settings
from core.ingestion import ResumeIngestionError, parse_resume_bytes
from core.jd import JDIngestionError, fetch_jd_url
from core.models import ExtractedRequirements, ResumeDocument
from core.pipeline import MatchPipeline
from core.redaction import redact_pii
from core.requirements import RequirementExtractionError, RequirementExtractor
from core.storage import (
    add_saved_resume,
    get_saved_resume,
    init_db,
    list_saved_resumes,
    load_saved_resume,
    remove_saved_resume,
    rename_saved_resume,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db(settings)
    yield


app = FastAPI(
    title="JevMatch API",
    version="0.1.0",
    description="Human-in-the-loop resume matching with TypeSafe Jev.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _resume_response(record) -> ResumeResponse:
    return ResumeResponse.model_validate(record, from_attributes=True)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": settings.jev_model}


@app.get("/resumes", response_model=list[ResumeResponse])
async def resumes_list() -> list[ResumeResponse]:
    return [_resume_response(record) for record in list_saved_resumes(settings)]


@app.post("/resumes", status_code=status.HTTP_201_CREATED)
async def resumes_upload(
    file: UploadFile = File(...),
    save: bool = Form(True),
    name: str | None = Form(None),
):
    content = await file.read(settings.max_file_bytes + 1)
    try:
        document = parse_resume_bytes(content, file.filename or "resume.txt", settings)
        if save:
            record = add_saved_resume(content, file.filename or "resume.txt", name, settings)
            return {"saved": True, "resume": _resume_response(record)}
        return {
            "saved": False,
            "resume": {
                "name": name or document.name,
                "text": document.text,
                "size_bytes": document.size_bytes,
            },
        }
    except ResumeIngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/resumes/{resume_id}", response_model=ResumeResponse)
async def resumes_rename(resume_id: str, request: RenameResumeRequest) -> ResumeResponse:
    try:
        return _resume_response(rename_saved_resume(resume_id, request.name, settings))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/resumes/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def resumes_delete(resume_id: str) -> Response:
    try:
        remove_saved_resume(resume_id, settings)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/jd/fetch", response_model=JDTextResponse)
async def jd_fetch(request: JDFetchRequest) -> JDTextResponse:
    try:
        return JDTextResponse(text=await fetch_jd_url(request.url, settings))
    except JDIngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/jd/requirements", response_model=ExtractedRequirements)
async def jd_requirements(request: RequirementRequest) -> ExtractedRequirements:
    try:
        return await RequirementExtractor(settings).extract(request.jd_text)
    except RequirementExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/match", response_model=MatchResponse)
async def match(request: MatchRequest) -> MatchResponse:
    if not request.resume_ids and not request.resumes:
        raise HTTPException(status_code=400, detail="Select or upload at least one resume.")
    try:
        documents: list[tuple[str | None, ResumeDocument]] = []
        for resume_id in request.resume_ids:
            if not get_saved_resume(resume_id, settings):
                raise HTTPException(status_code=404, detail=f"Resume not found: {resume_id}")
            documents.append((resume_id, load_saved_resume(resume_id, settings)))
        for inline in request.resumes:
            documents.append(
                (
                    None,
                    ResumeDocument(
                        name=inline.name,
                        text=inline.text,
                        redacted_text=redact_pii(inline.text),
                        size_bytes=len(inline.text.encode("utf-8")),
                    ),
                )
            )
        if request.requirements is not None:
            extracted = ExtractedRequirements(
                requirements=request.requirements,
                hard_constraints=request.hard_constraints,
            )
        elif request.jd_text:
            extracted = await RequirementExtractor(settings).extract(request.jd_text)
        else:
            raise HTTPException(status_code=400, detail="Provide requirements or JD text.")
        results = await MatchPipeline(settings).match_many(
            documents, extracted, include_evidence=request.include_evidence
        )
        return MatchResponse(results=results)
    except HTTPException:
        raise
    except (ResumeIngestionError, RequirementExtractionError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
