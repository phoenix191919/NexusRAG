from __future__ import annotations

import traceback
import uuid
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.graph.extractor import KnowledgeExtractor
from app.graph.neo4j_client import Neo4jGraph
from app.ingestion.extractors import extract_docx, extract_pdf, extract_txt, extract_youtube
from app.ingestion.sampler import select_chunks_for_extraction
from app.models.schemas import SourceRecord, SourceStatus, SourceType
from app.okf.bundle import OKFBundle
from app.rag.embeddings import VectorStore
from app.store import SourceStore


class IngestionPipeline:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.store = SourceStore()
        self.bundle = OKFBundle()
        self.vectors = VectorStore()
        self.extractor = KnowledgeExtractor()
        self.graph = Neo4jGraph()
        self.settings.upload_path.mkdir(parents=True, exist_ok=True)

    def create_file_source(self, filename: str, dest: Path, source_type: SourceType) -> SourceRecord:
        source_id = f"src_{uuid.uuid4().hex[:10]}"
        record = SourceRecord(
            source_id=source_id,
            title=filename,
            source_type=source_type,
            status=SourceStatus.UPLOADED,
            filename=str(dest),
            progress=5,
            progress_message="Uploaded",
        )
        return self.store.upsert(record)

    def create_youtube_source(self, url: str, title: Optional[str] = None) -> SourceRecord:
        source_id = f"yt_{uuid.uuid4().hex[:10]}"
        record = SourceRecord(
            source_id=source_id,
            title=title or url,
            source_type=SourceType.YOUTUBE,
            status=SourceStatus.UPLOADED,
            url=url,
            progress=5,
            progress_message="Queued",
        )
        return self.store.upsert(record)

    def process(self, source_id: str) -> None:
        rec = self.store.get(source_id)
        if not rec:
            return
        try:
            self.store.update_status(
                source_id, SourceStatus.PROCESSING, progress=10, message="Extracting text..."
            )
            chunks = []
            title = rec.title

            if rec.source_type == SourceType.PDF:
                chunks = extract_pdf(rec.filename, source_id)
            elif rec.source_type == SourceType.DOCX:
                chunks = extract_docx(rec.filename, source_id)
            elif rec.source_type == SourceType.TXT:
                chunks = extract_txt(rec.filename, source_id)
            elif rec.source_type == SourceType.YOUTUBE:
                title, chunks = extract_youtube(rec.url or "", source_id)
                rec.title = title
                self.store.upsert(rec)

            # Write OKF source concept
            body_preview = "\n\n".join(c.text[:500] for c in chunks[:3])
            meta = {"source_id": source_id, "source_type": rec.source_type.value}
            if rec.url:
                meta["resource"] = rec.url
            self.bundle.write_concept(
                self.bundle.source_concept_id(source_id),
                type_="Source",
                title=title,
                description=f"Ingested {rec.source_type.value} source",
                body=f"# Source\n\n{title}\n\n## Preview\n\n{body_preview}",
                sources=[{"id": source_id, "resource": rec.url or rec.filename or source_id, "title": title}],
                extra=meta,
            )

            self.store.update_status(
                source_id,
                SourceStatus.EMBEDDING,
                progress=35,
                message="Embedding chunks...",
                chunk_count=len(chunks),
            )
            self.vectors.upsert_chunks(chunks, extra_meta={"title": title})

            self.store.update_status(
                source_id,
                SourceStatus.EXTRACTING,
                progress=55,
                message="Extracting knowledge...",
            )
            # Embed all chunks above; extract only a smart budgeted sample
            sample = select_chunks_for_extraction(chunks, budget=8)
            entity_total = 0
            for i, chunk in enumerate(sample):
                extraction = self.extractor.extract_from_chunk(chunk, title)
                entity_total += self.extractor.apply_extraction(extraction, chunk, title)
                pct = 55 + int(30 * (i + 1) / max(1, len(sample)))
                self.store.update_status(
                    source_id,
                    SourceStatus.EXTRACTING,
                    progress=pct,
                    message=f"Extracting knowledge... ({i + 1}/{len(sample)})",
                    entity_count=entity_total,
                )

            self.store.update_status(
                source_id,
                SourceStatus.GRAPH_BUILDING,
                progress=90,
                message="Updating knowledge graph...",
            )
            g = self.bundle.build_link_graph()
            self.graph.clear_and_sync(g["nodes"], g["edges"])

            self.store.update_status(
                source_id,
                SourceStatus.COMPLETED,
                progress=100,
                message="Completed",
                chunk_count=len(chunks),
                entity_count=entity_total,
            )
        except Exception as e:
            traceback.print_exc()
            self.store.update_status(
                source_id,
                SourceStatus.FAILED,
                progress=100,
                message="Failed",
                error=str(e),
            )
