from __future__ import annotations

import re
from typing import Any

from app.graph.neo4j_client import Neo4jGraph
from app.models.schemas import Citation, QueryResponse
from app.okf.bundle import OKFBundle
from app.rag.embeddings import VectorStore
from app.rag.gemini import GeminiClient, friendly_gemini_error
from app.store import SourceStore


ANSWER_SYSTEM = """You are NexusRAG. Answer ONLY using the provided DOCUMENT CONTEXT and OKF CONCEPTS.

Citation rules (strict):
- Cite inline using ONLY the exact header of the evidence block you used, e.g. [Paper.pdf — page 14] or [Lecture — 14:32].
- Never invent a page number or timestamp. If a block has no page, omit the page.
- Do not cite table-of-contents or unrelated pages for content that came from another block.

List / "advantages" / "N points" questions:
- Enumerate every DISTINCT supported point found in the evidence.
- Do NOT invent extra points to hit a requested count (e.g. if asked for 10 but evidence supports 6, return 6 and say so).
- Put a citation on each bullet from the block that supports it.

If evidence conflicts, say so. If evidence is insufficient, say you do not know from the uploaded sources.
Be concise and precise.
"""

LIST_CUES = re.compile(
    r"\b(advantage|advantages|benefit|benefits|list|enumerate|points?|reasons?|"
    r"applications?|uses?|features?|ten|10|five|5|several|key)\b",
    re.I,
)


def _is_list_question(question: str) -> bool:
    return bool(LIST_CUES.search(question))


def _diversify_hits(hits: list[dict[str, Any]], limit: int = 12, per_page: int = 2) -> list[dict[str, Any]]:
    """Keep top scores but avoid one page/source dominating."""
    selected: list[dict[str, Any]] = []
    page_counts: dict[tuple[str, Any], int] = {}
    source_counts: dict[str, int] = {}
    seen_chunks: set[str] = set()

    for h in hits:
        chunk_id = h.get("chunk_id") or ""
        if chunk_id and chunk_id in seen_chunks:
            continue
        if h.get("kind") == "concept":
            # keep concepts lightly — up to 3
            concept_n = sum(1 for s in selected if s.get("kind") == "concept")
            if concept_n >= 3:
                continue
            selected.append(h)
            if chunk_id:
                seen_chunks.add(chunk_id)
            if len(selected) >= limit:
                break
            continue

        source_id = h.get("source_id") or ""
        page = h.get("page")
        key = (source_id, page)
        if page_counts.get(key, 0) >= per_page:
            continue
        if source_counts.get(source_id, 0) >= 5:
            continue
        page_counts[key] = page_counts.get(key, 0) + 1
        source_counts[source_id] = source_counts.get(source_id, 0) + 1
        selected.append(h)
        if chunk_id:
            seen_chunks.add(chunk_id)
        if len(selected) >= limit:
            break
    return selected


def _merge_hits(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for h in group:
            key = h.get("chunk_id") or h.get("concept_id") or f"{h.get('source_id')}:{h.get('text', '')[:40]}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(h)
    # Prefer higher score first
    merged.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
    return merged


class QueryEngine:
    def __init__(self) -> None:
        self.vectors = VectorStore()
        self.bundle = OKFBundle()
        self.graph = Neo4jGraph()
        self.gemini = GeminiClient()
        self.sources = SourceStore()

    def query(self, question: str) -> QueryResponse:
        try:
            primary = self.vectors.search(question, limit=24)
            extra: list[dict[str, Any]] = []
            if _is_list_question(question):
                # Second pass: applications/benefits phrasing to broaden coverage
                alt = re.sub(
                    r"\b(10|ten|list|enumerate|advantages?|benefits?)\b",
                    "applications benefits uses",
                    question,
                    flags=re.I,
                )
                if alt.strip().lower() != question.strip().lower():
                    extra = self.vectors.search(alt, limit=16)
                # Domain-focused alt for QM/nanotech style questions
                if re.search(r"nanotechnolog|quantum", question, re.I):
                    extra = _merge_hits(
                        extra,
                        self.vectors.search(
                            "quantum confinement quantum dots nanowires tunneling "
                            "semiconductors density functional theory metamaterials "
                            "quantum sensors entanglement nanotechnology applications",
                            limit=16,
                        ),
                    )
            hits = _diversify_hits(_merge_hits(primary, extra), limit=14, per_page=2)
        except Exception as e:
            return QueryResponse(
                answer=friendly_gemini_error(e),
                citations=[],
                graph={"nodes": [], "edges": []},
                conflicts=[],
                confidence="Low",
            )

        entity_hints = self._entity_hints(question)
        graph = self.graph.neighborhood(entity_hints, limit=40)
        if not graph["nodes"]:
            concept_ids = [h.get("concept_id") for h in hits if h.get("concept_id")]
            if concept_ids:
                graph = self.graph.neighborhood(concept_ids, limit=40)

        concept_blocks = []
        for n in graph.get("nodes") or []:
            c = self.bundle.get_concept(n["id"])
            if c:
                concept_blocks.append(
                    f"### {c['title']} (`{c['id']}`)\n{c.get('description') or ''}\n{(c.get('body') or '')[:1200]}"
                )

        doc_blocks = []
        citations: list[Citation] = []
        seen = set()
        used_pages: set[tuple[str, Any]] = set()

        for h in hits:
            if h.get("kind") == "concept":
                continue
            text = h.get("text") or ""
            source_id = h.get("source_id") or ""
            title = h.get("title") or source_id
            rec = self.sources.get(source_id)
            if rec:
                title = rec.title
            page = h.get("page")
            ts = h.get("timestamp_start")
            te = h.get("timestamp_end")
            loc = ""
            if page is not None:
                loc = f"page {page}"
                used_pages.add((source_id, page))
            elif ts:
                loc = f"{ts}" + (f"-{te}" if te else "")
            header = f"[{title}{' — ' + loc if loc else ''}]"
            doc_blocks.append(f"{header}\n{text}")
            key = (source_id, page, ts, h.get("chunk_id"))
            if key not in seen:
                seen.add(key)
                citations.append(
                    Citation(
                        source_id=source_id,
                        title=title,
                        page=page,
                        timestamp_start=ts,
                        timestamp_end=te,
                        chunk_id=h.get("chunk_id"),
                        concept_id=h.get("concept_id"),
                    )
                )

        # Drop citations whose page was never in used evidence (hygiene)
        citations = [
            c
            for c in citations
            if c.page is None or (c.source_id, c.page) in used_pages or c.timestamp_start
        ]

        graph_context = "\n".join(
            f"- {e['source']} --{e.get('label')}--> {e['target']}" for e in (graph.get("edges") or [])[:40]
        )

        conflicts = []
        for n in graph.get("nodes") or []:
            c = self.bundle.get_concept(n["id"])
            if c and "# Potential conflicts" in (c.get("body") or ""):
                conflicts.append(f"{c['title']}: has potential conflict notes in OKF")

        list_note = ""
        if _is_list_question(question):
            list_note = (
                "\nThis is a list-style question. Return every distinct supported point "
                "from DOCUMENT CONTEXT; do not pad to a requested count.\n"
            )

        prompt = f"""QUESTION: {question}
{list_note}
GRAPH CONTEXT:
{graph_context or '(none)'}

OKF CONCEPTS:
{chr(10).join(concept_blocks) or '(none)'}

DOCUMENT CONTEXT:
{chr(10).join(doc_blocks) or '(none)'}

Write a grounded answer with citations that match evidence headers exactly.
"""
        try:
            answer = self.gemini.generate_text(prompt, system=ANSWER_SYSTEM)
        except Exception as e:
            answer = friendly_gemini_error(e)

        confidence = "High" if len(doc_blocks) >= 4 else ("Medium" if doc_blocks else "Low")
        return QueryResponse(
            answer=answer,
            citations=citations[:12],
            graph=graph,
            conflicts=conflicts,
            confidence=confidence,
        )

    def _entity_hints(self, question: str) -> list[str]:
        hints: list[str] = []
        q = question.lower()
        for c in self.bundle.list_concepts():
            if c["type"] == "Source":
                continue
            title = c.get("title") or ""
            if len(title) >= 3 and title.lower() in q:
                hints.append(c["id"])
                hints.append(title)
        # Only call Gemini if title matching found nothing (saves tokens)
        if not hints:
            try:
                data = self.gemini.generate_json(
                    f'Extract entity names from this question as JSON {{"entities":["..."]}}: {question}'
                )
                for name in (data.get("entities") if isinstance(data, dict) else []) or []:
                    hints.append(str(name))
                    found = self.bundle.find_by_title_or_alias(str(name))
                    if found:
                        hints.append(found["id"])
            except Exception:
                pass
        return hints
