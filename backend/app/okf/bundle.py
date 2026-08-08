from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

import frontmatter
import yaml
from slugify import slugify

from app.config import get_settings
from app.models.schemas import utc_now_iso

RESERVED = {"index.md", "log.md"}
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


class OKFBundle:
    """OKF v0.2 bundle reader/writer (canonical knowledge store)."""

    def __init__(self, root: Optional[Path] = None):
        settings = get_settings()
        self.root = Path(root) if root else settings.bundle_path
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "entities").mkdir(exist_ok=True)
        (self.root / "sources").mkdir(exist_ok=True)
        self._ensure_root_index()

    def _ensure_root_index(self) -> None:
        index = self.root / "index.md"
        if not index.exists():
            index.write_text(
                "---\nokf_version: \"0.2\"\n---\n\n"
                "# NexusRAG Knowledge Bundle\n\n"
                "* [Entities](entities/) - Extracted concepts\n"
                "* [Sources](sources/) - Uploaded documents and transcripts\n",
                encoding="utf-8",
            )
        log = self.root / "log.md"
        if not log.exists():
            log.write_text("# Bundle Update Log\n\n", encoding="utf-8")

    def concept_path(self, concept_id: str) -> Path:
        rel = concept_id if concept_id.endswith(".md") else f"{concept_id}.md"
        return self.root / rel

    def concept_id_from_path(self, path: Path) -> str:
        rel = path.relative_to(self.root).as_posix()
        return rel[:-3] if rel.endswith(".md") else rel

    def list_concepts(self) -> list[dict[str, Any]]:
        concepts = []
        for path in self.root.rglob("*.md"):
            if path.name in RESERVED:
                continue
            try:
                post = frontmatter.load(path)
            except Exception:
                continue
            cid = self.concept_id_from_path(path)
            concepts.append(
                {
                    "id": cid,
                    "type": post.get("type", "Entity"),
                    "title": post.get("title") or path.stem,
                    "description": post.get("description"),
                    "tags": post.get("tags") or [],
                    "status": post.get("status", "stable"),
                    "generated": post.get("generated"),
                    "verified": post.get("verified"),
                    "sources": post.get("sources") or [],
                    "body": post.content,
                    "path": str(path),
                }
            )
        return concepts

    def get_concept(self, concept_id: str) -> Optional[dict[str, Any]]:
        path = self.concept_path(concept_id)
        if not path.exists():
            return None
        post = frontmatter.load(path)
        return {
            "id": concept_id,
            "type": post.get("type", "Entity"),
            "title": post.get("title") or path.stem,
            "description": post.get("description"),
            "tags": post.get("tags") or [],
            "status": post.get("status", "stable"),
            "generated": post.get("generated"),
            "verified": post.get("verified"),
            "sources": post.get("sources") or [],
            "stale_after": post.get("stale_after"),
            "body": post.content,
            "meta": {k: v for k, v in post.metadata.items()},
        }

    def write_concept(
        self,
        concept_id: str,
        *,
        type_: str,
        title: str,
        body: str,
        description: Optional[str] = None,
        tags: Optional[list[str]] = None,
        sources: Optional[list[dict[str, Any]]] = None,
        status: str = "stable",
        extra: Optional[dict[str, Any]] = None,
        actor: str = "nexusrag/gemini-3.5-flash",
    ) -> Path:
        path = self.concept_path(concept_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        meta: dict[str, Any] = {
            "type": type_,
            "title": title,
            "status": status,
            "generated": {"by": actor, "at": utc_now_iso()},
        }
        if description:
            meta["description"] = description
        if tags:
            meta["tags"] = tags
        if sources:
            meta["sources"] = sources
        if extra:
            meta.update(extra)
        post = frontmatter.Post(body.strip() + "\n", **meta)
        path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
        self._append_log(f"**Update**: Wrote [{title}](/{concept_id}.md).")
        self._refresh_indexes()
        return path

    def merge_aliases(self, concept_id: str, aliases: list[str]) -> None:
        concept = self.get_concept(concept_id)
        if not concept:
            return
        meta = concept.get("meta") or {}
        existing = list(meta.get("aliases") or [])
        for a in aliases:
            if a and a not in existing and a.lower() != (concept.get("title") or "").lower():
                existing.append(a)
        path = self.concept_path(concept_id)
        post = frontmatter.load(path)
        post["aliases"] = existing
        post["generated"] = {"by": "nexusrag/gemini-3.5-flash", "at": utc_now_iso()}
        path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")

    def append_conflict_note(self, concept_id: str, note: str) -> None:
        concept = self.get_concept(concept_id)
        if not concept:
            return
        path = self.concept_path(concept_id)
        post = frontmatter.load(path)
        body = post.content.rstrip()
        if "# Potential conflicts" not in body:
            body += "\n\n# Potential conflicts\n\n"
        body += f"- {note}\n"
        post.content = body
        post["status"] = post.get("status") or "stable"
        path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")

    def parse_links(self, body: str, from_id: str) -> list[tuple[str, str, str]]:
        """Return list of (label, target_concept_id, link_text)."""
        edges = []
        for match in LINK_RE.finditer(body or ""):
            text, href = match.group(1), match.group(2)
            if href.startswith("http://") or href.startswith("https://"):
                continue
            target = self._resolve_href(href, from_id)
            if target:
                edges.append((text, target, match.group(0)))
        return edges

    def _resolve_href(self, href: str, from_id: str) -> Optional[str]:
        href = href.split("#")[0].strip()
        if not href:
            return None
        if href.startswith("/"):
            rel = href[1:]
        else:
            base = Path(from_id).parent
            rel = (base / href).as_posix()
        if rel.endswith(".md"):
            rel = rel[:-3]
        # normalize ./
        parts = []
        for p in rel.split("/"):
            if p in ("", "."):
                continue
            if p == "..":
                if parts:
                    parts.pop()
                continue
            parts.append(p)
        return "/".join(parts)

    def build_link_graph(self) -> dict[str, Any]:
        nodes = []
        edges = []
        seen_edges = set()
        for c in self.list_concepts():
            nodes.append(
                {
                    "id": c["id"],
                    "label": c["title"],
                    "type": c["type"],
                    "description": c.get("description"),
                }
            )
            for label, target, _ in self.parse_links(c.get("body") or "", c["id"]):
                key = (c["id"], target, label.lower())
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                edges.append({"source": c["id"], "target": target, "label": label})
        return {"nodes": nodes, "edges": edges}

    def find_by_title_or_alias(self, name: str) -> Optional[dict[str, Any]]:
        key = _normalize_name(name)
        for c in self.list_concepts():
            if c["type"] == "Source":
                continue
            if _normalize_name(c["title"]) == key:
                return c
            aliases = (c.get("meta") or {}).get("aliases") if "meta" in c else None
            # reload aliases from file
            full = self.get_concept(c["id"])
            if not full:
                continue
            for a in full.get("meta", {}).get("aliases") or []:
                if _normalize_name(a) == key:
                    return full
            if _normalize_name(full["title"]) == key:
                return full
        return None

    def entity_slug(self, name: str) -> str:
        return f"entities/{slugify(name, lowercase=True)}"

    def source_concept_id(self, source_id: str) -> str:
        return f"sources/{source_id}"

    def _append_log(self, line: str) -> None:
        log = self.root / "log.md"
        today = utc_now_iso()[:10]
        content = log.read_text(encoding="utf-8") if log.exists() else "# Bundle Update Log\n\n"
        heading = f"## {today}"
        if heading in content:
            content = content.replace(heading, f"{heading}\n* {line}", 1)
        else:
            content = content.rstrip() + f"\n\n{heading}\n* {line}\n"
        log.write_text(content, encoding="utf-8")

    def _refresh_indexes(self) -> None:
        self._write_dir_index(self.root / "entities", "Entities")
        self._write_dir_index(self.root / "sources", "Sources")

    def _write_dir_index(self, directory: Path, title: str) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        lines = [f"# {title}\n"]
        for path in sorted(directory.glob("*.md")):
            if path.name == "index.md":
                continue
            try:
                post = frontmatter.load(path)
                t = post.get("title") or path.stem
                d = post.get("description") or ""
                lines.append(f"* [{t}]({path.name}) - {d}".rstrip(" -"))
            except Exception:
                lines.append(f"* [{path.stem}]({path.name})")
        (directory / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def stats(self) -> dict[str, int]:
        concepts = self.list_concepts()
        entities = [c for c in concepts if c["type"] != "Source"]
        sources = [c for c in concepts if c["type"] == "Source"]
        graph = self.build_link_graph()
        return {
            "entities": len(entities),
            "sources": len(sources),
            "relationships": len(graph["edges"]),
        }


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def dump_yaml(data: Any) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
