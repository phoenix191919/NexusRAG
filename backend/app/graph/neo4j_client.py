from __future__ import annotations

from typing import Any, Optional

from neo4j import GraphDatabase

from app.config import get_settings


class Neo4jGraph:
    def __init__(self) -> None:
        settings = get_settings()
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

    def close(self) -> None:
        self.driver.close()

    def upsert_entity(self, concept_id: str, title: str, type_: str, description: str = "") -> None:
        with self.driver.session() as session:
            session.run(
                """
                MERGE (e:Entity {id: $id})
                SET e.title = $title, e.type = $type, e.description = $description
                """,
                id=concept_id,
                title=title,
                type=type_,
                description=description or "",
            )

    def upsert_rel(self, source_id: str, target_id: str, label: str) -> None:
        with self.driver.session() as session:
            session.run(
                """
                MERGE (a:Entity {id: $source})
                MERGE (b:Entity {id: $target})
                MERGE (a)-[r:RELATED {label: $label}]->(b)
                """,
                source=source_id,
                target=target_id,
                label=label or "related_to",
            )

    def clear_and_sync(self, nodes: list[dict], edges: list[dict]) -> None:
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            for n in nodes:
                if n.get("type") == "Source":
                    continue
                session.run(
                    """
                    MERGE (e:Entity {id: $id})
                    SET e.title = $title, e.type = $type, e.description = $description
                    """,
                    id=n["id"],
                    title=n.get("label") or n["id"],
                    type=n.get("type") or "Entity",
                    description=n.get("description") or "",
                )
            for e in edges:
                session.run(
                    """
                    MATCH (a:Entity {id: $source})
                    MATCH (b:Entity {id: $target})
                    MERGE (a)-[r:RELATED {label: $label}]->(b)
                    """,
                    source=e["source"],
                    target=e["target"],
                    label=e.get("label") or "related_to",
                )

    def neighborhood(self, titles_or_ids: list[str], limit: int = 30) -> dict[str, Any]:
        if not titles_or_ids:
            return {"nodes": [], "edges": []}
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (e:Entity)
                WHERE e.id IN $ids OR toLower(e.title) IN $names
                OPTIONAL MATCH (e)-[r:RELATED]-(n:Entity)
                RETURN e, r, n
                LIMIT $limit
                """,
                ids=titles_or_ids,
                names=[t.lower() for t in titles_or_ids],
                limit=limit,
            )
            nodes: dict[str, dict] = {}
            edges = []
            seen = set()
            for record in result:
                e = record["e"]
                if e:
                    nodes[e["id"]] = {
                        "id": e["id"],
                        "label": e.get("title") or e["id"],
                        "type": e.get("type") or "Entity",
                        "description": e.get("description"),
                    }
                n = record["n"]
                r = record["r"]
                if n:
                    nodes[n["id"]] = {
                        "id": n["id"],
                        "label": n.get("title") or n["id"],
                        "type": n.get("type") or "Entity",
                        "description": n.get("description"),
                    }
                if e and n and r:
                    key = (e["id"], n["id"], r.get("label"))
                    if key not in seen:
                        seen.add(key)
                        edges.append(
                            {
                                "source": e["id"],
                                "target": n["id"],
                                "label": r.get("label") or "related_to",
                            }
                        )
            return {"nodes": list(nodes.values()), "edges": edges}

    def count_entities(self) -> int:
        with self.driver.session() as session:
            rec = session.run("MATCH (e:Entity) RETURN count(e) AS c").single()
            return int(rec["c"]) if rec else 0

    def count_rels(self) -> int:
        with self.driver.session() as session:
            rec = session.run("MATCH ()-[r:RELATED]->() RETURN count(r) AS c").single()
            return int(rec["c"]) if rec else 0
