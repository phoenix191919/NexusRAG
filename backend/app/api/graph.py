from fastapi import APIRouter, HTTPException

from app.models.schemas import StatsResponse
from app.okf.bundle import OKFBundle
from app.rag.embeddings import VectorStore
from app.store import SourceStore

router = APIRouter(prefix="/api", tags=["graph"])


@router.get("/graph")
async def get_graph():
    bundle = OKFBundle()
    return bundle.build_link_graph()


@router.get("/graph/entity/{entity_id:path}")
async def get_entity(entity_id: str):
    bundle = OKFBundle()
    concept = bundle.get_concept(entity_id)
    if not concept:
        raise HTTPException(404, "Entity not found")
    links = bundle.parse_links(concept.get("body") or "", entity_id)
    return {
        **concept,
        "links": [{"label": a, "target": b} for a, b, _ in links],
    }


@router.get("/concepts")
async def list_concepts():
    bundle = OKFBundle()
    return bundle.list_concepts()


@router.get("/stats", response_model=StatsResponse)
async def stats():
    store = SourceStore()
    bundle = OKFBundle()
    bstats = bundle.stats()
    try:
        chunks = VectorStore().count()
    except Exception:
        chunks = 0
    return StatsResponse(
        sources=len(store.list()),
        chunks=chunks,
        entities=bstats["entities"],
        relationships=bstats["relationships"],
    )
