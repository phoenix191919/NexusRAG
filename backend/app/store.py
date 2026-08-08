from __future__ import annotations

import json
import threading
from typing import Optional

from app.config import get_settings
from app.models.schemas import SourceRecord, SourceStatus, utc_now_iso


class SourceStore:
    """Simple JSON file store for source processing state."""

    def __init__(self) -> None:
        settings = get_settings()
        self.path = settings.data_path / "sources.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")

    def _read(self) -> dict:
        with self._lock:
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                return {}

    def _write(self, data: dict) -> None:
        with self._lock:
            self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def upsert(self, record: SourceRecord) -> SourceRecord:
        data = self._read()
        record.updated_at = utc_now_iso()
        data[record.source_id] = record.model_dump()
        self._write(data)
        return record

    def get(self, source_id: str) -> Optional[SourceRecord]:
        data = self._read()
        raw = data.get(source_id)
        return SourceRecord(**raw) if raw else None

    def list(self) -> list[SourceRecord]:
        data = self._read()
        records = [SourceRecord(**v) for v in data.values()]
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records

    def update_status(
        self,
        source_id: str,
        status: SourceStatus,
        *,
        progress: int = 0,
        message: str = "",
        error: Optional[str] = None,
        chunk_count: Optional[int] = None,
        entity_count: Optional[int] = None,
    ) -> Optional[SourceRecord]:
        rec = self.get(source_id)
        if not rec:
            return None
        rec.status = status
        rec.progress = progress
        if message:
            rec.progress_message = message
        if error is not None:
            rec.error = error
        if chunk_count is not None:
            rec.chunk_count = chunk_count
        if entity_count is not None:
            rec.entity_count = entity_count
        return self.upsert(rec)
