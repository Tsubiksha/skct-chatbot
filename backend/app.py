import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.app.graph_rag.router import service as sqlite_graph_rag_service
from backend.config import get_settings
from backend.embeddings.chroma_store import ChromaVectorStore
from backend.embeddings.ollama_client import OllamaClient
from backend.graph.sqlite_store import SQLiteKnowledgeStore
from backend.models import (
    HealthResponse,
    IngestRequest,
    IngestResponse,
    GraphStatsResponse,
    QueryRequest,
    QueryResponse,
    ScrapeRequest,
    ScrapeResponse,
)
from backend.rag.graphrag_engine import GraphRAGEngine
from backend.scraper.web_scraper import CollegeScraper

settings = get_settings()

ollama = OllamaClient(
    base_url=settings.ollama_base_url,
    llm_model=settings.ollama_llm_model,
    embed_model=settings.ollama_embed_model,
)
vector_store = ChromaVectorStore(settings.chroma_path, settings.chroma_collection)
graph_store = SQLiteKnowledgeStore()
rag_engine = GraphRAGEngine(settings, ollama, vector_store, graph_store)


@asynccontextmanager
async def lifespan(app: FastAPI):
    auto_ingest_task: asyncio.Task | None = None
    if settings.auto_ingest_on_startup:
        auto_ingest_task = asyncio.create_task(_prepare_knowledge_base())
    yield
    if auto_ingest_task and not auto_ingest_task.done():
        auto_ingest_task.cancel()
    await graph_store.close()


async def _prepare_knowledge_base() -> None:
    try:
        await rag_engine.ingest_if_needed(max_pages=settings.auto_ingest_max_pages)
    except Exception as exc:
        rag_engine.last_ingest_message = f"Automatic ChromaDB indexing failed: {exc}"

    try:
        sqlite_stats = sqlite_graph_rag_service.stats()
        if sqlite_stats.get("chunks", 0) == 0:
            await sqlite_graph_rag_service.scrape_website(
                force_reindex=False,
                max_pages=settings.sqlite_auto_ingest_max_pages,
                max_depth=2,
            )
    except Exception:
        pass


app = FastAPI(
    title="AI College Knowledge Assistant",
    description="Real GraphRAG backend using FastAPI, Ollama, ChromaDB, and Neo4j.",
    version="1.0.0",
    lifespan=lifespan,
)

# Local development can involve several frontend ports. "*" prevents browser
# CORS failures while the app is being run locally.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_model=HealthResponse)
async def root() -> HealthResponse:
    return await health()


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    chroma_count = await vector_store.count()
    graph_status = await graph_store.health()
    sqlite_status = "unavailable"
    try:
        sqlite_stats = sqlite_graph_rag_service.stats()
        sqlite_status = f"active ({sqlite_stats.get('chunks', 0)} chunks)"
    except Exception:
        pass

    query_status = "indexing" if rag_engine.is_ingesting else "real-graphrag-ready" if chroma_count > 0 else "needs-ingestion"
    return HealthResponse(
        status="ok",
        services={
            "backend": "online",
            "ollama": await ollama.health(),
            "chroma": f"ok ({chroma_count} chunks)",
            "sqlite": sqlite_status,
            "sqlite_graph": graph_status,
            "query": query_status,
            "indexing": rag_engine.last_ingest_message,
        },
    )


@app.post("/scrape", response_model=ScrapeResponse)
async def scrape(request: ScrapeRequest) -> ScrapeResponse:
    try:
        scraper = CollegeScraper(
            base_url=str(request.base_url or settings.college_base_url),
            max_pages=request.max_pages or settings.max_scrape_pages,
            keywords=request.keywords,
        )
        documents = await scraper.scrape()
        rag_engine.last_documents = documents
        return ScrapeResponse(pages_scraped=len(documents), documents=documents)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {exc}") from exc


@app.post("/ingest", response_model=IngestResponse)
async def ingest(request: IngestRequest) -> IngestResponse:
    try:
        return await rag_engine.ingest(
            scrape_first=request.scrape_first,
            reset=request.reset,
            max_pages=request.max_pages,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}") from exc


@app.get("/graph-stats", response_model=GraphStatsResponse)
async def graph_stats() -> GraphStatsResponse:
    chunks = await vector_store.count()
    try:
        stats = await graph_store.stats()
    except Exception:
        stats = {}

    return GraphStatsResponse(
        departments=stats.get("departments", 0),
        faculty=stats.get("faculty", 0),
        courses=stats.get("courses", 0),
        companies=stats.get("companies", 0),
        events=stats.get("events", 0),
        relationships=stats.get("relationships", 0),
        chunks=chunks,
    )


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse:
    try:
        q = request.question or request.query
        if not q:
            raise HTTPException(status_code=400, detail="Query or question is required")
        return await rag_engine.answer(q, request.top_k)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"GraphRAG query failed: {exc}") from exc
