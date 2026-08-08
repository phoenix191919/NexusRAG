from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import get_settings
from app.ingestion.pipeline import IngestionPipeline
from app.models.schemas import SourceRecord, SourceType, YouTubeRequest

router = APIRouter(prefix="/api/sources", tags=["sources"])
_executor = ThreadPoolExecutor(max_workers=2)
_pipeline: IngestionPipeline | None = None


def get_pipeline() -> IngestionPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = IngestionPipeline()
    return _pipeline


@router.post("/upload", response_model=SourceRecord)
async def upload_source(file: UploadFile = File(...)):
    settings = get_settings()
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    name = file.filename or "upload.bin"
    suffix = Path(name).suffix.lower()
    type_map = {
        ".pdf": SourceType.PDF,
        ".docx": SourceType.DOCX,
        ".txt": SourceType.TXT,
        ".md": SourceType.TXT,
    }
    if suffix not in type_map:
        raise HTTPException(400, "Supported types: PDF, DOCX, TXT, MD")

    pipeline = get_pipeline()
    dest = settings.upload_path / f"{Path(name).stem}_{Path(name).suffix}"
    # unique
    i = 0
    while dest.exists():
        i += 1
        dest = settings.upload_path / f"{Path(name).stem}_{i}{suffix}"

    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    record = pipeline.create_file_source(name, dest, type_map[suffix])
    # fix filename path on record
    record.filename = str(dest)
    pipeline.store.upsert(record)
    _executor.submit(pipeline.process, record.source_id)
    return record


@router.post("/youtube", response_model=SourceRecord)
async def youtube_source(body: YouTubeRequest):
    if "youtube.com" not in body.url and "youtu.be" not in body.url:
        raise HTTPException(400, "Provide a valid YouTube URL")
    pipeline = get_pipeline()
    record = pipeline.create_youtube_source(body.url, body.title)
    _executor.submit(pipeline.process, record.source_id)
    return record


@router.get("", response_model=list[SourceRecord])
async def list_sources():
    return get_pipeline().store.list()


@router.get("/{source_id}", response_model=SourceRecord)
async def get_source(source_id: str):
    rec = get_pipeline().store.get(source_id)
    if not rec:
        raise HTTPException(404, "Source not found")
    return rec
