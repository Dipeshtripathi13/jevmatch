from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

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
from core.ingestion import ResumeIngestionError, parse_resume_bytes, parse_resume_text
from core.jd import JDIngestionError, fetch_jd_url
from core.models import ExtractedRequirements, ResumeDocument
from core.pipeline import MatchPipeline
from core.rate_limit import SlidingWindowRateLimiter
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
rate_limiter = SlidingWindowRateLimiter(settings.rate_limit_max_clients)
match_pipeline = MatchPipeline(settings)


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


def _rate_limit_for(request: Request) -> tuple[str, int]:
    if request.method == "POST" and request.url.path == "/match":
        return "match", settings.match_rate_limit_per_window
    if request.method == "POST" and request.url.path == "/resumes":
        return "upload", settings.upload_rate_limit_per_window
    if request.method == "POST" and request.url.path in {"/jd/fetch", "/jd/requirements"}:
        return "extraction", settings.extraction_rate_limit_per_window
    return "default", settings.default_rate_limit_per_window


@app.middleware("http")
async def request_security_limits(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.max_request_bytes:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": "Request body exceeds the configured size limit."},
                )
        except ValueError:
            return JSONResponse(
                status_code=400, content={"detail": "Invalid Content-Length header."}
            )

    if not settings.rate_limit_enabled or request.url.path in {
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    }:
        return await call_next(request)

    bucket, limit = _rate_limit_for(request)
    client_host = request.client.host if request.client else "unknown"
    decision = await rate_limiter.check(
        f"{client_host}:{bucket}",
        limit=limit,
        window_seconds=settings.rate_limit_window_seconds,
    )
    headers = {
        "X-RateLimit-Limit": str(decision.limit),
        "X-RateLimit-Remaining": str(decision.remaining),
        "X-RateLimit-Reset": str(decision.retry_after_seconds),
    }
    if not decision.allowed:
        headers["Retry-After"] = str(decision.retry_after_seconds)
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded. Try again later."},
            headers=headers,
        )
    response = await call_next(request)
    response.headers.update(headers)
    return response


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
    name: str | None = Form(None, max_length=255),
):
    content = await file.read(settings.max_file_bytes + 1)
    try:
        document = await run_in_threadpool(
            parse_resume_bytes, content, file.filename or "resume.txt", settings
        )
        if save:
            record = await run_in_threadpool(
                add_saved_resume, content, file.filename or "resume.txt", name, settings
            )
            return {
                "saved": True,
                "resume": _resume_response(record),
                "security_flags": document.security_flags,
            }
        return {
            "saved": False,
            "security_flags": document.security_flags,
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


@app.post("/requirements/validate", response_model=ExtractedRequirements)
async def requirements_validate(request: ExtractedRequirements) -> ExtractedRequirements:
    """Validate and normalize user-supplied criteria without calling Anthropic."""
    return request


@app.post("/match", response_model=MatchResponse)
async def match(request: MatchRequest) -> MatchResponse:
    if not request.resume_ids and not request.resumes:
        raise HTTPException(status_code=400, detail="Select or upload at least one resume.")
    if len(request.resume_ids) + len(request.resumes) > settings.max_resumes_per_match:
        raise HTTPException(
            status_code=400,
            detail=f"A match request may contain at most {settings.max_resumes_per_match} resumes.",
        )
    try:
        documents: list[tuple[str | None, ResumeDocument]] = []
        for resume_id in request.resume_ids:
            if not get_saved_resume(resume_id, settings):
                raise HTTPException(status_code=404, detail=f"Resume not found: {resume_id}")
            document = await run_in_threadpool(load_saved_resume, resume_id, settings)
            documents.append((resume_id, document))
        for inline in request.resumes:
            documents.append(
                (
                    None,
                    parse_resume_text(inline.text, inline.name, settings),
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
        if len(extracted.requirements) > settings.max_requirements_per_match:
            raise HTTPException(
                status_code=400,
                detail=(
                    "A match may contain at most "
                    f"{settings.max_requirements_per_match} requirements."
                ),
            )
        results = await match_pipeline.match_many(
            documents, extracted, include_evidence=request.include_evidence
        )
        return MatchResponse(results=results)
    except HTTPException:
        raise
    except ResumeIngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RequirementExtractionError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# Wrap the whole FastAPI application so even unexpected server errors receive CORS headers.
app = CORSMiddleware(
    app=app,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
