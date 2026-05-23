import json
import ollama
import httpx
from typing import List, Dict, Any, AsyncGenerator
from backend.app.config import settings

class ResponseGenerator:
    def __init__(self):
        self.model = settings.LLM_MODEL
        self.base_url = settings.OLLAMA_BASE_URL

    def _build_prompt(self, query: str, context_chunks: List[Dict[str, Any]], graph_context: List[Dict[str, Any]]) -> str:
        context_str = ""
        for i, chunk in enumerate(context_chunks):
            title = chunk.get("title", "Source Page")
            url = chunk.get("url", "")
            text = chunk.get("chunk_text", "")
            context_str += f"--- Source [{i+1}]: {title} ({url}) ---\n{text}\n\n"
            
        graph_str = ""
        for rel in graph_context:
            src = rel.get("source_name")
            tgt = rel.get("target_name")
            rtype = rel.get("relationship_type")
            graph_str += f"- {src} -[{rtype}]-> {tgt}\n"
        if not graph_str:
            graph_str = "No graph relationship context available."

        prompt = f"""You are the official AI Assistant for Sri Krishna College of Technology (SKCT).
Use the supplied website context and graph relationships to answer the user query.

Rules:
1. Base your answer ONLY on the provided context. Do not invent details, faculty, or placement numbers.
2. If the context does not contain the answer, reply EXACTLY with: "I could not find this information on the SKCT website."
3. Keep the tone professional, friendly, and helpful. Use clear markdown for bullet points and lists.
4. Briefly mention source URLs if relevant.

Context Data:
{context_str}

Graph Context:
{graph_str}

User Query: {query}

Grounded Answer:"""
        return prompt

    async def generate_stream(self, query: str, context_chunks: List[Dict[str, Any]], graph_context: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        prompt = self._build_prompt(query, context_chunks, graph_context)
        
        try:
            client = ollama.AsyncClient(host=self.base_url)
            response = await client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a highly accurate, strict educational assistant. Answer ONLY using the context. Never hallucinate."},
                    {"role": "user", "content": prompt}
                ],
                stream=True
            )
            
            async for chunk in response:
                if 'message' in chunk and 'content' in chunk['message']:
                    yield chunk['message']['content']
                    
        except Exception as e:
            yield f"\n\n[System Error: Failed to connect to LLM - {str(e)}]"
