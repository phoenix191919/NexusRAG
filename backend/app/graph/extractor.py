from __future__ import annotations

from typing import Any, Optional

from app.models.schemas import Chunk
from app.okf.bundle import OKFBundle, _normalize_name
from app.rag.gemini import GeminiClient
from app.rag.embeddings import VectorStore


EXTRACT_SYSTEM = """You extract knowledge for an OKF (Open Knowledge Format) knowledge bundle.
Return ONLY valid JSON with this shape:
{
  "entities": [
    {"name": "...", "type": "Entity|Model|Technique|Organization|Concept", "description": "...", "aliases": []}
  ],
  "relationships": [
    {"source": "EntityName", "relation": "is_a|uses|developed_by|related_to|part_of", "target": "EntityName", "evidence": "short quote"}
  ],
  "conflicts": [
    {"entity": "...", "note": "possible contradiction with prior knowledge if any"}
  ]
}
Use clear canonical entity names. Prefer well-known names (BERT, Transformer, Google).
Only extract facts grounded in the provided text.
"""


class KnowledgeExtractor:
    def __init__(self) -> None:
        self.gemini = GeminiClient()
        self.bundle = OKFBundle()
        self.vectors = VectorStore()

    def extract_from_chunk(self, chunk: Chunk, source_title: str) -> dict[str, Any]:
        loc = ""
        if chunk.page is not None:
            loc = f"page {chunk.page}"
        elif chunk.timestamp_start:
            loc = f"{chunk.timestamp_start}-{chunk.timestamp_end or ''}"
        prompt = f"""Source: {source_title} ({chunk.source_id}) {loc}
Chunk ID: {chunk.chunk_id}

Text:
{chunk.text}
"""
        try:
            data = self.gemini.generate_json(prompt, system=EXTRACT_SYSTEM)
            if not isinstance(data, dict):
                return {"entities": [], "relationships": [], "conflicts": []}
            return {
                "entities": data.get("entities") or [],
                "relationships": data.get("relationships") or [],
                "conflicts": data.get("conflicts") or [],
            }
        except Exception as e:
            print(f"[extract] failed for {chunk.chunk_id}: {e}")
            return {"entities": [], "relationships": [], "conflicts": []}

    def resolve_entity(self, name: str, description: str = "", aliases: Optional[list[str]] = None) -> dict[str, Any]:
        """Find or create canonical OKF concept."""
        aliases = aliases or []
        existing = self.bundle.find_by_title_or_alias(name)
        if existing:
            self.bundle.merge_aliases(existing["id"], [name, *aliases])
            return existing

        # Similarity via vector search on concepts
        hits = self.vectors.search(f"{name}. {description}", limit=5)
        for h in hits:
            if h.get("kind") != "concept":
                continue
            title = h.get("title") or ""
            if _normalize_name(title) and (
                _normalize_name(title) == _normalize_name(name)
                or _normalize_name(name) in _normalize_name(title)
                or _normalize_name(title) in _normalize_name(name)
            ):
                cid = h.get("concept_id")
                if cid:
                    concept = self.bundle.get_concept(cid)
                    if concept:
                        self.bundle.merge_aliases(cid, [name, *aliases])
                        return concept

        # LLM confirmation when a close concept exists
        candidates = [h for h in hits if h.get("kind") == "concept"][:3]
        if candidates:
            try:
                confirm = self.gemini.generate_json(
                    f"""Does the entity "{name}" ({description}) match any of these existing concepts?
Concepts: {[{"id": c.get("concept_id"), "title": c.get("title"), "text": (c.get("text") or "")[:300]} for c in candidates]}
Return {{"match_id": "concept_id or null", "reason": "..."}}""",
                    system="You resolve entity identity. Return JSON only.",
                )
                mid = confirm.get("match_id") if isinstance(confirm, dict) else None
                if mid:
                    concept = self.bundle.get_concept(mid)
                    if concept:
                        self.bundle.merge_aliases(mid, [name, *aliases])
                        return concept
            except Exception:
                pass

        # Create new
        cid = self.bundle.entity_slug(name)
        body = description or f"{name} is a concept in the knowledge base."
        self.bundle.write_concept(
            cid,
            type_="Entity",
            title=name,
            description=description or None,
            body=body,
            tags=aliases[:5] if aliases else None,
            extra={"aliases": aliases} if aliases else None,
        )
        return self.bundle.get_concept(cid) or {"id": cid, "title": name, "type": "Entity"}

    def apply_extraction(
        self,
        extraction: dict[str, Any],
        chunk: Chunk,
        source_title: str,
    ) -> int:
        """Write/update OKF concepts and return entity count touched."""
        sid = chunk.source_id
        loc_title = source_title
        if chunk.page is not None:
            loc_title = f"{source_title} — page {chunk.page}"
        elif chunk.timestamp_start:
            loc_title = f"{source_title} — {chunk.timestamp_start}"

        source_entry = {
            "id": f"{chunk.chunk_id}",
            "resource": f"/sources/{sid}.md",
            "title": loc_title,
        }

        id_by_name: dict[str, str] = {}
        count = 0
        for ent in extraction.get("entities") or []:
            name = (ent.get("name") or "").strip()
            if not name:
                continue
            concept = self.resolve_entity(
                name,
                description=ent.get("description") or "",
                aliases=ent.get("aliases") or [],
            )
            cid = concept["id"]
            id_by_name[name] = cid
            id_by_name[_normalize_name(name)] = cid

            # Update body with provenance footnote if missing
            full = self.bundle.get_concept(cid)
            if not full:
                continue
            sources = list(full.get("sources") or [])
            if not any(s.get("id") == source_entry["id"] for s in sources):
                sources.append(source_entry)
            body = full.get("body") or ""
            footnote = f"[^{chunk.chunk_id}]"
            if footnote not in body:
                desc = ent.get("description") or full.get("description") or name
                body = body.rstrip() + f"\n\n{desc}{footnote}\n\n{footnote}: {loc_title}\n"
            type_name = ent.get("type") or full.get("type") or "Entity"
            self.bundle.write_concept(
                cid,
                type_=type_name if type_name != "Source" else "Entity",
                title=full.get("title") or name,
                description=full.get("description") or ent.get("description"),
                body=body,
                tags=full.get("tags") or [],
                sources=sources,
                extra={"aliases": (full.get("meta") or {}).get("aliases") or ent.get("aliases") or []},
            )
            text_for_embed = f"{full.get('title') or name}\n{body}"
            self.vectors.upsert_concept(cid, full.get("title") or name, text_for_embed, type_name)
            count += 1

        # Relationships as markdown links
        for rel in extraction.get("relationships") or []:
            src_name = (rel.get("source") or "").strip()
            tgt_name = (rel.get("target") or "").strip()
            relation = (rel.get("relation") or "related_to").strip()
            if not src_name or not tgt_name:
                continue
            src = id_by_name.get(src_name) or id_by_name.get(_normalize_name(src_name))
            tgt = id_by_name.get(tgt_name) or id_by_name.get(_normalize_name(tgt_name))
            if not src:
                c = self.resolve_entity(src_name)
                src = c["id"]
            if not tgt:
                c = self.resolve_entity(tgt_name)
                tgt = c["id"]
            src_concept = self.bundle.get_concept(src)
            if not src_concept:
                continue
            link = f"[{relation}](/{tgt}.md)"
            body = src_concept.get("body") or ""
            evidence = rel.get("evidence") or ""
            line = f"\n- {src_concept.get('title')} {link} {tgt_name}."
            if evidence:
                line += f" _{evidence}_"
            line += f"[^{chunk.chunk_id}]\n"
            if f"](/{tgt}.md)" not in body or relation.lower() not in body.lower():
                body = body.rstrip() + "\n" + line
                if f"[^{chunk.chunk_id}]:" not in body:
                    body += f"\n[^{chunk.chunk_id}]: {loc_title}\n"
                self.bundle.write_concept(
                    src,
                    type_=src_concept.get("type") or "Entity",
                    title=src_concept.get("title") or src_name,
                    description=src_concept.get("description"),
                    body=body,
                    tags=src_concept.get("tags") or [],
                    sources=src_concept.get("sources") or [source_entry],
                    extra={"aliases": (src_concept.get("meta") or {}).get("aliases") or []},
                )

        for conflict in extraction.get("conflicts") or []:
            ent = (conflict.get("entity") or "").strip()
            note = (conflict.get("note") or "").strip()
            if not ent or not note:
                continue
            c = self.bundle.find_by_title_or_alias(ent)
            if c:
                self.bundle.append_conflict_note(c["id"], f"{note} (from {loc_title})")

        return count
