import sqlite3
import random
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, List
from backend.app.graph_rag.graph_rag_service import GraphRAGService

router = APIRouter(prefix="/api/graph-rag", tags=["GraphRAG Operations"])
service = GraphRAGService()

class ScrapeRequest(BaseModel):
    force_reindex: bool = False
    max_pages: int = Field(default=30, ge=1, le=100)
    max_depth: int = Field(default=2, ge=0, le=4)

@router.post("/scrape-website")
async def scrape_website(req: ScrapeRequest):
    try:
        res = await service.scrape_website(
            force_reindex=req.force_reindex,
            max_pages=req.max_pages,
            max_depth=req.max_depth
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_stats():
    return service.stats()

@router.get("/health")
async def get_health():
    return await service.health()

@router.get("/graph-data")
async def get_graph_data():
    """Fetch nodes and edges from SQLite formatted for React Flow."""
    try:
        from backend.database import get_connection
        
        with get_connection() as conn:
            # Get unique entities
            entity_rows = conn.execute("""
                SELECT MIN(id) as id, entity_type, name 
                FROM entities 
                GROUP BY entity_type, name
            """).fetchall()
            
            # Get relationships
            rel_rows = conn.execute("""
                SELECT id, source_type, source_name, relationship_type, target_type, target_name 
                FROM relationships
            """).fetchall()

        nodes = []
        edges = []
        
        # Color mapping for entity types
        colors = {
            "Department": "#10b981", # Emerald
            "Faculty": "#3b82f6",     # Blue
            "Course": "#8b5cf6",     # Purple
            "Company": "#f59e0b",    # Amber
            "Event": "#ec4899",      # Pink
            "College": "#ef4444",    # Red
            "Club": "#06b6d4",       # Cyan
            "Lab": "#14b8a6",        # Teal
            "Research Area": "#a855f7", # Light Purple
        }

        # Lay out nodes in a broad area so they don't overlay
        for idx, row in enumerate(entity_rows):
            e_type = row["entity_type"]
            e_name = row["name"]
            node_id = f"{e_type}_{e_name}"
            
            # Assign random position in a 1200x800 box
            x = random.randint(50, 1150)
            y = random.randint(50, 750)
            
            nodes.append({
                "id": node_id,
                "type": "custom",
                "data": {
                    "label": e_name,
                    "type": e_type,
                    "color": colors.get(e_type, "#64748b")
                },
                "position": {"x": x, "y": y}
            })

        for row in rel_rows:
            s_type = row["source_type"]
            s_name = row["source_name"]
            t_type = row["target_type"]
            t_name = row["target_name"]
            rel_type = row["relationship_type"]
            
            source_id = f"{s_type}_{s_name}"
            target_id = f"{t_type}_{t_name}"
            edge_id = f"e_{row['id']}"
            
            edges.append({
                "id": edge_id,
                "source": source_id,
                "target": target_id,
                "label": rel_type,
                "animated": True,
                "style": {"stroke": "#475569", "strokeWidth": 1.5}
            })
            
        return {"nodes": nodes, "edges": edges}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch graph data: {str(e)}")
