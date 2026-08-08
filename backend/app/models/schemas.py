from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class SourceStatus(str, Enum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    EXTRACTING = "EXTRACTING"
    EMBEDDING = "EMBEDDING"
    GRAPH_BUILDING = "GRAPH_BUILDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SourceType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    YOUTUBE = "youtube"


class Chunk(BaseModel):
    chunk_id: str
    source_id: str
    text: str
    page: Optional[int] = None
    timestamp_start: Optional[str] = None
    timestamp_end: Optional[str] = None
    section: Optional[str] = None


class SourceRecord(BaseModel):
    source_id: str
    title: str
    source_type: SourceType
    status: SourceStatus = SourceStatus.UPLOADED
    filename: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None
    chunk_count: int = 0
    entity_count: int = 0
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    progress: int = 0
    progress_message: str = "Queued"


class Citation(BaseModel):
    source_id: str
    title: str
    page: Optional[int] = None
    timestamp_start: Optional[str] = None
    timestamp_end: Optional[str] = None
    chunk_id: Optional[str] = None
    concept_id: Optional[str] = None


class GraphNode(BaseModel):
    id: str
    label: str
    type: str = "Entity"
    description: Optional[str] = None


class GraphEdge(BaseModel):
    source: str
    target: str
    label: str = "related_to"


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation] = []
    graph: dict[str, Any] = Field(default_factory=lambda: {"nodes": [], "edges": []})
    conflicts: list[str] = []
    confidence: Optional[str] = None


class YouTubeRequest(BaseModel):
    url: str
    title: Optional[str] = None


class StatsResponse(BaseModel):
    sources: int
    chunks: int
    entities: int
    relationships: int
