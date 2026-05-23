import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="SKCT College AI Assistant",
    description="Production-grade GraphRAG backend with FastAPI, Ollama, ChromaDB, and SQLite.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from backend.database import init_db

# Initialize database
init_db()

@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "SKCT AI Assistant Backend is running."}

from .routes import auth, chat, graph_rag
app.include_router(auth.router, prefix="/api/auth")
app.include_router(chat.router, prefix="/api/chat")
app.include_router(graph_rag.router, prefix="/api/graph-rag")

from backend.models import QueryRequest
from backend.app.graph_rag.graph_rag_query_service import graph_rag_query

@app.post("/query")
async def query_root_endpoint(request: QueryRequest):
    q = request.question or request.query
    if not q:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Query or question content is required")
    try:
        res = await graph_rag_query(q)
        return res
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))
