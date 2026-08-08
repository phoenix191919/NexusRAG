from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import graph, query, upload
from app.config import get_settings
from app.okf.bundle import OKFBundle

settings = get_settings()

app = FastAPI(title="NexusRAG", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(query.router)
app.include_router(graph.router)


@app.on_event("startup")
def startup() -> None:
    settings.bundle_path.mkdir(parents=True, exist_ok=True)
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    OKFBundle()  # ensure index/log


@app.get("/api/health")
def health():
    return {"status": "ok", "okf_version": "0.2"}
