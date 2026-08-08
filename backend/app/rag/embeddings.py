from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.config import get_settings
from app.models.schemas import Chunk
from app.rag.gemini import GeminiClient


class VectorStore:
    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self.client = QdrantClient(url=settings.qdrant_url)
        self.gemini = GeminiClient()
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        name = self.settings.qdrant_collection
        existing = [c.name for c in self.client.get_collections().collections]
        if name not in existing:
            self.client.create_collection(
                collection_name=name,
                vectors_config=qm.VectorParams(
                    size=self.settings.embedding_dims,
                    distance=qm.Distance.COSINE,
                ),
            )

    def upsert_chunks(self, chunks: list[Chunk], extra_meta: Optional[dict[str, Any]] = None) -> int:
        if not chunks:
            return 0
        texts = [c.text for c in chunks]
        vectors = self.gemini.embed(texts)
        points = []
        for chunk, vector in zip(chunks, vectors):
            payload = {
                "chunk_id": chunk.chunk_id,
                "source_id": chunk.source_id,
                "text": chunk.text,
                "page": chunk.page,
                "timestamp_start": chunk.timestamp_start,
                "timestamp_end": chunk.timestamp_end,
                "section": chunk.section,
                "kind": "chunk",
            }
            if extra_meta:
                payload.update(extra_meta)
            points.append(
                qm.PointStruct(
                    id=str(uuid4()),
                    vector=vector,
                    payload=payload,
                )
            )
        self.client.upsert(collection_name=self.settings.qdrant_collection, points=points)
        return len(points)

    def upsert_concept(self, concept_id: str, title: str, text: str, concept_type: str) -> None:
        vector = self.gemini.embed([text[:6000]])[0]
        self.client.upsert(
            collection_name=self.settings.qdrant_collection,
            points=[
                qm.PointStruct(
                    id=str(uuid4()),
                    vector=vector,
                    payload={
                        "concept_id": concept_id,
                        "title": title,
                        "text": text[:4000],
                        "type": concept_type,
                        "kind": "concept",
                    },
                )
            ],
        )

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        vector = self.gemini.embed_query(query)
        if not vector:
            return []
        hits = self.client.search(
            collection_name=self.settings.qdrant_collection,
            query_vector=vector,
            limit=limit,
            with_payload=True,
        )
        results = []
        for h in hits:
            payload = h.payload or {}
            results.append({**payload, "score": h.score})
        return results

    def count(self) -> int:
        info = self.client.get_collection(self.settings.qdrant_collection)
        return int(info.points_count or 0)

    def delete_by_source(self, source_id: str) -> None:
        self.client.delete(
            collection_name=self.settings.qdrant_collection,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[qm.FieldCondition(key="source_id", match=qm.MatchValue(value=source_id))]
                )
            ),
        )
