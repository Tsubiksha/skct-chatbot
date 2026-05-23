import sqlite3
import json
import httpx
import asyncio
import chromadb
from typing import List, Dict, Any
from backend.app.config import settings

class HybridRetriever:
    def __init__(self, graph_storage=None):
        self.graph_storage = graph_storage
        self.chroma_client = chromadb.PersistentClient(path=str(settings.CHROMA_DB_DIR))
        self.collection = self.chroma_client.get_or_create_collection(
            name="college_knowledge",
            metadata={"hnsw:space": "cosine"}
        )
        self.db_path = settings.GRAPH_DB_PATH

    async def _get_embedding(self, text: str) -> List[float]:
        """Fetch embedding from local Ollama client."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                    json={"model": settings.EMBEDDING_MODEL, "prompt": text}
                )
                response.raise_for_status()
                return response.json()["embedding"]
        except Exception as e:
            print(f"Error fetching embedding for '{text[:20]}': {e}")
            # Return dummy zero embedding if it fails
            return [0.0] * 768

    async def _expand_query(self, query: str) -> List[str]:
        """Generate 3 alternative search queries using Ollama."""
        try:
            prompt = (
                f"You are an assistant. Given this search query: '{query}', "
                f"generate 3 alternative, semantically similar search phrases for retrieving documents from a college website. "
                f"Output only the 3 alternative queries, one per line. Do not number them or add any other text."
            )
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/generate",
                    json={"model": settings.LLM_MODEL, "prompt": prompt, "stream": False}
                )
                response.raise_for_status()
                lines = response.json().get("response", "").strip().split("\n")
                expanded = [query]
                for line in lines:
                    cleaned = line.strip().strip("-").strip("*").strip("123456789. ")
                    if cleaned and cleaned.lower() != query.lower():
                        expanded.append(cleaned)
                return list(dict.fromkeys(expanded))[:4] # Keep original + max 3 expanded
        except Exception as e:
            print(f"Query expansion failed: {e}")
            return [query]

    def _fts_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search SQLite using FTS5."""
        candidates = []
        try:
            # Clean punctuation for FTS matching
            clean_query = query.replace("'", "''")
            # We want to match individual words
            terms = [f'"{t}"' for t in clean_query.split() if len(t) > 2]
            if not terms:
                terms = [f'"{clean_query}"']
            fts_expression = " OR ".join(terms)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                # Query FTS table and join with website_chunks to fetch metadata
                cursor.execute("""
                    SELECT 
                        wc.id, wc.title, wc.url, wc.page_type, wc.chunk_text, wc.chunk_index
                    FROM website_chunks wc
                    JOIN website_chunks_fts fts ON wc.id = fts.rowid
                    WHERE website_chunks_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """, (fts_expression, limit))
                
                for row in cursor.fetchall():
                    candidates.append(dict(row))
        except Exception as e:
            print(f"FTS search failed: {e}")
        return candidates

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        dot_product = sum(x * y for x, y in zip(vec1, vec2))
        norm1 = sum(x * x for x in vec1) ** 0.5
        norm2 = sum(x * x for x in vec2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Run the hybrid search pipeline."""
        # 1. Query Expansion
        queries = await self._expand_query(query)
        
        # 2. Get embeddings for queries
        query_embeddings = await asyncio.gather(*(self._get_embedding(q) for q in queries))
        primary_emb = query_embeddings[0]

        # 3. Vector Search
        vector_candidates = []
        try:
            # Query chroma using multiple expanded queries
            for emb in query_embeddings:
                res = self.collection.query(
                    query_embeddings=[emb],
                    n_results=top_k * 2,
                    include=["documents", "metadatas", "distances", "embeddings"]
                )
                if res and res["documents"]:
                    for idx, doc in enumerate(res["documents"][0]):
                        meta = res["metadatas"][0][idx]
                        dist = res["distances"][0][idx]
                        chroma_id = res["ids"][0][idx]
                        emb_val = res["embeddings"][0][idx] if res["embeddings"] else None
                        
                        # Store candidate
                        vector_candidates.append({
                            "id": chroma_id,
                            "title": meta.get("title", "Untitled"),
                            "url": meta.get("source_url", ""),
                            "chunk_text": doc,
                            "chunk_index": meta.get("chunk_index", 0),
                            "embedding": emb_val,
                            "vector_score": 1.0 - dist # Cosine similarity
                        })
        except Exception as e:
            print(f"Chroma Vector search failed: {e}")

        # 4. FTS Search
        fts_candidates = []
        for q in queries:
            fts_candidates.extend(self._fts_search(q, limit=top_k * 2))

        # Deduplicate FTS candidates
        fts_by_id = {}
        for c in fts_candidates:
            fts_by_id[c["id"]] = c

        # 5. Merge candidates
        # We need a unique set of all candidates by URL + snippet (or by text/title)
        merged_candidates = {}
        
        # Add vector candidates
        for c in vector_candidates:
            key = (c["url"], c["chunk_text"][:100])
            if key not in merged_candidates:
                merged_candidates[key] = {
                    "title": c["title"],
                    "url": c["url"],
                    "chunk_text": c["chunk_text"],
                    "chunk_index": c["chunk_index"],
                    "embedding": c["embedding"],
                    "score": c["vector_score"]
                }

        # Add FTS candidates that weren't captured by vector search
        for cid, c in fts_by_id.items():
            key = (c["url"], c["chunk_text"][:100])
            if key not in merged_candidates:
                # If we don't have its embedding, we fetch it from Chroma or generate it
                emb_val = None
                try:
                    # Try retrieving from Chroma by comparing URL or metadata
                    chroma_res = self.collection.get(
                        where={"source_url": c["url"]},
                        include=["documents", "embeddings"]
                    )
                    if chroma_res and chroma_res["documents"]:
                        for idx, doc in enumerate(chroma_res["documents"]):
                            if doc[:100] == c["chunk_text"][:100]:
                                emb_val = chroma_res["embeddings"][idx] if chroma_res["embeddings"] else None
                                break
                except Exception:
                    pass
                
                if emb_val is None:
                    # Generate embedding if missing (fallback)
                    emb_val = await self._get_embedding(c["chunk_text"])

                # Calculate cosine similarity with primary query
                score = self._cosine_similarity(primary_emb, emb_val) if emb_val else 0.3
                
                merged_candidates[key] = {
                    "title": c["title"],
                    "url": c["url"],
                    "chunk_text": c["chunk_text"],
                    "chunk_index": c["chunk_index"],
                    "embedding": emb_val,
                    "score": score
                }

        # 6. Rerank based on Cosine Similarity of their embeddings to the primary query
        candidates_list = list(merged_candidates.values())
        for c in candidates_list:
            if c["embedding"]:
                c["score"] = self._cosine_similarity(primary_emb, c["embedding"])
            else:
                c["score"] = 0.0
            # Clean embedding from final response to save payload size
            c.pop("embedding", None)

        # Sort descending by score
        candidates_list.sort(key=lambda x: x["score"], reverse=True)
        return candidates_list[:top_k]
