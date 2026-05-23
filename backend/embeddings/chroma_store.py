import asyncio
import os

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.models import Chunk, RetrievedSource


class ChromaVectorStore:
    def __init__(self, path: str, collection_name: str):
        self.client = chromadb.PersistentClient(
            path=path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    async def reset(self) -> None:
        await asyncio.to_thread(self._reset_sync)

    def _reset_sync(self) -> None:
        name = self.collection.name
        self.client.delete_collection(name)
        self.collection = self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    async def upsert_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if not chunks:
            return

        def write() -> None:
            self.collection.upsert(
                ids=[chunk.id for chunk in chunks],
                embeddings=embeddings,
                documents=[chunk.text for chunk in chunks],
                metadatas=[
                    {
                        "source_url": chunk.source_url,
                        "title": chunk.title,
                        "chunk_index": chunk.chunk_index,
                    }
                    for chunk in chunks
                ],
            )

        await asyncio.to_thread(write)

    async def search(self, query_embedding: list[float], top_k: int) -> list[RetrievedSource]:
        def read() -> list[RetrievedSource]:
            result = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )
            sources: list[RetrievedSource] = []
            for text, metadata, distance in zip(
                result.get("documents", [[]])[0],
                result.get("metadatas", [[]])[0],
                result.get("distances", [[]])[0],
            ):
                sources.append(
                    RetrievedSource(
                        title=str(metadata.get("title", "Untitled")),
                        url=str(metadata.get("source_url", "")),
                        snippet=text[:700],
                        score=float(distance),
                    )
                )
            return sources

        return await asyncio.to_thread(read)

    async def get_by_source_urls(self, urls: list[str], limit_per_url: int = 2) -> list[RetrievedSource]:
        def read() -> list[RetrievedSource]:
            sources: list[RetrievedSource] = []
            for url in urls:
                result = self.collection.get(
                    where={"source_url": url},
                    limit=limit_per_url,
                    include=["documents", "metadatas"],
                )
                for text, metadata in zip(result.get("documents", []), result.get("metadatas", [])):
                    sources.append(
                        RetrievedSource(
                            title=str(metadata.get("title", "Untitled")),
                            url=str(metadata.get("source_url", "")),
                            snippet=text[:700],
                            score=None,
                        )
                    )
            return sources

        return await asyncio.to_thread(read)

    async def count(self) -> int:
        return await asyncio.to_thread(self.collection.count)
