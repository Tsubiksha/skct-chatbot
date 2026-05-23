from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.graph_rag.graph_rag_query_service import graph_rag_query
from backend.app.graph_rag.graph_rag_service import GraphRAGService

router = APIRouter(prefix="/api/graph-rag", tags=["SQLite GraphRAG"])
service = GraphRAGService()


class ScrapeWebsiteRequest(BaseModel):
    force_reindex: bool = False
    max_pages: int = Field(default=30, ge=1, le=60)
    max_depth: int = Field(default=2, ge=0, le=4)


class QueryRequest(BaseModel):
    question: str | None = Field(default=None)
    query: str | None = Field(default=None)


@router.post("/scrape-website")
async def scrape_website(request: ScrapeWebsiteRequest) -> dict:
    try:
        return await service.scrape_website(
            force_reindex=request.force_reindex,
            max_pages=request.max_pages,
            max_depth=request.max_depth,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Website scraping failed: {exc}") from exc


@router.get("/website-search")
async def website_search(query: str = Query(min_length=1), limit: int = Query(default=5, ge=1, le=20)) -> dict:
    return {"results": service.search(query, limit=limit)}


@router.get("/stats")
async def stats() -> dict:
    return service.stats()


@router.get("/scraped-pages")
async def scraped_pages() -> dict:
    return {"pages": service.scraped_pages()}


@router.get("/health")
async def graph_rag_health() -> dict:
    return await service.health()


@router.post("/query")
async def query(request: QueryRequest) -> dict:
    try:
        q = request.question or request.query
        if not q:
            raise HTTPException(status_code=400, detail="Query or question is required")
        return await graph_rag_query(q)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"GraphRAG query failed: {exc}") from exc


@router.get("/graph-stats")
async def graph_stats() -> dict:
    return service.stats()
