import asyncio
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura

from core.config import Settings, get_settings


class JDIngestionError(ValueError):
    pass


async def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise JDIngestionError("Job URL must use http or https and include a hostname.")
    try:
        records = await asyncio.to_thread(
            socket.getaddrinfo,
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
        )
    except socket.gaierror as exc:
        raise JDIngestionError("Could not resolve the job posting hostname.") from exc
    for record in records:
        address = ipaddress.ip_address(record[4][0])
        if not address.is_global:
            raise JDIngestionError("Job URL resolves to a private or non-public network address.")


async def fetch_jd_url(url: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    current = url
    headers = {"User-Agent": "JevMatch/0.1 (+https://github.com/Dipeshtripathi13/jevmatch)"}
    async with httpx.AsyncClient(timeout=settings.fetch_timeout_seconds, headers=headers) as client:
        for _ in range(4):
            await _validate_public_url(current)
            try:
                async with client.stream("GET", current, follow_redirects=False) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise JDIngestionError("Job URL redirected without a destination.")
                        current = urljoin(current, location)
                        continue
                    response.raise_for_status()
                    content_length = int(response.headers.get("content-length", "0") or 0)
                    if content_length > settings.max_jd_bytes:
                        raise JDIngestionError("Job page exceeds the download size limit.")
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > settings.max_jd_bytes:
                            raise JDIngestionError("Job page exceeds the download size limit.")
                        chunks.append(chunk)
                    html = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
                    break
            except httpx.HTTPError as exc:
                raise JDIngestionError(f"Could not fetch the job posting: {exc}") from exc
        else:
            raise JDIngestionError("Job URL redirected too many times.")

    text = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
    text = text.strip()
    if len(text) < settings.min_jd_chars:
        raise JDIngestionError(
            "The page did not expose enough job-description text. Paste the description instead."
        )
    return text


def read_jd_file(path: Path | str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    path = Path(path)
    if not path.is_file():
        raise JDIngestionError(f"Job description file not found: {path}")
    if path.stat().st_size > settings.max_jd_bytes:
        raise JDIngestionError("Job description exceeds the file-size limit.")
    try:
        text = path.read_text(encoding="utf-8-sig").strip()
    except UnicodeDecodeError as exc:
        raise JDIngestionError("Job description files must use UTF-8 encoding.") from exc
    if not text:
        raise JDIngestionError("Job description is empty.")
    return text
