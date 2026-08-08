from __future__ import annotations

import re
from typing import Optional

import fitz  # PyMuPDF
from docx import Document
from youtube_transcript_api import YouTubeTranscriptApi

from app.models.schemas import Chunk


def extract_pdf(path: str, source_id: str) -> list[Chunk]:
    doc = fitz.open(path)
    pages: list[tuple[int, str]] = []
    for i, page in enumerate(doc):
        text = page.get_text("text").strip()
        if text:
            pages.append((i + 1, text))
    doc.close()
    return chunk_pages(pages, source_id)


def extract_docx(path: str, source_id: str) -> list[Chunk]:
    document = Document(path)
    text = "\n".join(p.text for p in document.paragraphs if p.text.strip())
    return chunk_text(text, source_id)


def extract_txt(path: str, source_id: str) -> list[Chunk]:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    return chunk_text(text, source_id)


def extract_youtube(url: str, source_id: str) -> tuple[str, list[Chunk]]:
    video_id = _youtube_id(url)
    if not video_id:
        raise ValueError("Could not parse YouTube video id from URL")
    transcript = YouTubeTranscriptApi.get_transcript(video_id)
    title = f"YouTube {video_id}"
    chunks: list[Chunk] = []
    # Group ~ roughly 500-800 tokens worth of transcript lines (~350 words)
    buf: list[str] = []
    start = None
    end = None
    idx = 0
    word_count = 0
    for item in transcript:
        t = item.get("text", "").replace("\n", " ").strip()
        if not t:
            continue
        if start is None:
            start = _fmt_ts(item.get("start", 0))
        end = _fmt_ts(item.get("start", 0) + item.get("duration", 0))
        buf.append(t)
        word_count += len(t.split())
        if word_count >= 350:
            chunks.append(
                Chunk(
                    chunk_id=f"{source_id}_c{idx}",
                    source_id=source_id,
                    text=" ".join(buf),
                    timestamp_start=start,
                    timestamp_end=end,
                )
            )
            idx += 1
            buf, start, end, word_count = [], None, None, 0
    if buf:
        chunks.append(
            Chunk(
                chunk_id=f"{source_id}_c{idx}",
                source_id=source_id,
                text=" ".join(buf),
                timestamp_start=start,
                timestamp_end=end,
            )
        )
    return title, chunks


def chunk_pages(pages: list[tuple[int, str]], source_id: str, target_words: int = 550, overlap_words: int = 80) -> list[Chunk]:
    chunks: list[Chunk] = []
    idx = 0
    for page_num, text in pages:
        words = text.split()
        if not words:
            continue
        start = 0
        while start < len(words):
            end = min(len(words), start + target_words)
            piece = " ".join(words[start:end]).strip()
            if piece:
                chunks.append(
                    Chunk(
                        chunk_id=f"{source_id}_c{idx}",
                        source_id=source_id,
                        text=piece,
                        page=page_num,
                    )
                )
                idx += 1
            if end >= len(words):
                break
            start = max(end - overlap_words, start + 1)
    return chunks


def chunk_text(text: str, source_id: str, target_words: int = 550, overlap_words: int = 80) -> list[Chunk]:
    words = text.split()
    chunks: list[Chunk] = []
    idx = 0
    start = 0
    while start < len(words):
        end = min(len(words), start + target_words)
        piece = " ".join(words[start:end]).strip()
        if piece:
            chunks.append(
                Chunk(
                    chunk_id=f"{source_id}_c{idx}",
                    source_id=source_id,
                    text=piece,
                )
            )
            idx += 1
        if end >= len(words):
            break
        start = max(end - overlap_words, start + 1)
    return chunks


def _youtube_id(url: str) -> Optional[str]:
    patterns = [
        r"(?:v=|/shorts/|youtu\.be/)([A-Za-z0-9_-]{6,})",
        r"^([A-Za-z0-9_-]{11})$",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def _fmt_ts(seconds: float) -> str:
    total = int(seconds)
    m, s = divmod(total, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
