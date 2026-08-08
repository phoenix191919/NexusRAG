from fastapi import APIRouter

from app.models.schemas import QueryRequest, QueryResponse
from app.rag.retriever import QueryEngine

router = APIRouter(prefix="/api", tags=["query"])
_engine: QueryEngine | None = None


def get_engine() -> QueryEngine:
    global _engine
    if _engine is None:
        _engine = QueryEngine()
    return _engine


@router.post("/query", response_model=QueryResponse)
async def query(body: QueryRequest):
    if not body.question.strip():
        return QueryResponse(answer="Please ask a question.")
    try:
        return get_engine().query(body.question.strip())
    except Exception as e:
        from app.rag.gemini import friendly_gemini_error

        return QueryResponse(
            answer=friendly_gemini_error(e),
            citations=[],
            graph={"nodes": [], "edges": []},
            conflicts=[],
            confidence="Low",
        )
