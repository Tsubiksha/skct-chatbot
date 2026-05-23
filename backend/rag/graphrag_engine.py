import asyncio

from backend.config import Settings
from backend.embeddings.chroma_store import ChromaVectorStore
from backend.embeddings.ollama_client import OllamaClient
from backend.models import IngestResponse, QueryResponse, RetrievedSource, SourceDocument
from backend.rag.entity_extractor import EntityExtractor
from backend.scraper.web_scraper import CollegeScraper
from backend.utils.text import chunk_documents

EMBEDDING_BATCH_SIZE = 16
COURSE_SOURCE_URLS = [
    "https://skct.edu.in/departments",
    "https://skct.edu.in/academics",
    "https://skct.edu.in/academics/departments",
]


class GraphRAGEngine:
    def __init__(
        self,
        settings: Settings,
        ollama: OllamaClient,
        vector_store: ChromaVectorStore,
        graph_store,
    ):
        self.settings = settings
        self.ollama = ollama
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.extractor = EntityExtractor()
        self.last_documents: list[SourceDocument] = []
        self._ingest_lock = asyncio.Lock()
        self.is_ingesting = False
        self.last_ingest_message = "idle"

    async def scrape(self, max_pages: int | None = None) -> list[SourceDocument]:
        scraper = CollegeScraper(
            base_url=self.settings.college_base_url,
            max_pages=max_pages or self.settings.max_scrape_pages,
        )
        self.last_documents = await scraper.scrape()
        return self.last_documents

    async def ingest(self, scrape_first: bool = True, reset: bool = False, max_pages: int | None = None) -> IngestResponse:
        async with self._ingest_lock:
            self.is_ingesting = True
            self.last_ingest_message = "Scraping SKCT website..."
            try:
                return await self._ingest(scrape_first=scrape_first, reset=reset, max_pages=max_pages)
            finally:
                self.is_ingesting = False

    async def ingest_if_needed(self, max_pages: int | None = None) -> IngestResponse | None:
        if await self.vector_store.count() > 0:
            self.last_ingest_message = "ChromaDB already has indexed website chunks."
            return None
        return await self.ingest(scrape_first=True, reset=False, max_pages=max_pages)

    async def _ingest(self, scrape_first: bool = True, reset: bool = False, max_pages: int | None = None) -> IngestResponse:
        if reset:
            await self.vector_store.reset()
            try:
                await self.graph_store.reset()
            except Exception:
                pass

        self.last_ingest_message = "Scraping SKCT website..."
        documents = await self.scrape(max_pages=max_pages) if scrape_first or not self.last_documents else self.last_documents
        chunks = chunk_documents(
            documents,
            chunk_size=self.settings.chunk_size,
            overlap=self.settings.chunk_overlap,
        )
        if not chunks:
            return IngestResponse(
                documents=len(documents),
                chunks=0,
                graph_entities={"relationships": 0, "graph_status": "not_started"},
                message="No usable text chunks were found. Try increasing max_pages or checking the website scraper.",
            )

        self.last_ingest_message = "Saving scraped pages and chunks in SQLite..."
        if hasattr(self.graph_store, "upsert_documents_and_chunks"):
            await self.graph_store.upsert_documents_and_chunks(documents, chunks)

        self.last_ingest_message = f"Embedding and storing {len(chunks)} chunks in ChromaDB..."
        for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch = chunks[start : start + EMBEDDING_BATCH_SIZE]
            embeddings: list[list[float]] = []
            for chunk in batch:
                embeddings.append(await self.ollama.embed(chunk.text))
            await self.vector_store.upsert_chunks(batch, embeddings)
            self.last_ingest_message = f"Stored {min(start + len(batch), len(chunks))}/{len(chunks)} chunks in ChromaDB."

        self.last_ingest_message = "Extracting graph entities..."
        extracted = self.extractor.extract(chunks)
        try:
            counts = await self.graph_store.upsert_extracted_graph(extracted)
            counts["graph_status"] = "sqlite-active"
            message = "Ingestion completed. ChromaDB vectors and SQLite knowledge graph are ready."
        except Exception:
            counts = {
                "Department": len(extracted.get("Department", [])),
                "Faculty": len(extracted.get("Faculty", [])),
                "Company": len(extracted.get("Company", [])),
                "Course": len(extracted.get("Course", [])),
                "Event": len(extracted.get("Event", [])),
                "relationships": 0,
                "graph_status": "unavailable",
            }
            message = (
                "Vector ingestion completed, but SQLite graph indexing failed. "
                "The assistant can still answer from ChromaDB sources."
            )

        self.last_ingest_message = message
        return IngestResponse(
            documents=len(documents),
            chunks=len(chunks),
            graph_entities=counts,
            message=message,
        )

    async def answer(self, question: str, top_k: int) -> QueryResponse:
        top_k = min(top_k, self.settings.retrieval_top_k)
        chunk_count = await self.vector_store.count()
        if chunk_count == 0:
            if self.is_ingesting:
                raise ValueError("The SKCT website is still being indexed. Please ask again in a moment.")
            raise ValueError("No college data has been ingested yet. Click Ingest Website first, then ask your question.")

        query_embedding = await self.ollama.embed(question)
        sources = await self.vector_store.search(query_embedding, top_k=top_k)
        sources = await self._boost_sources(question, sources)
        if not sources:
            raise ValueError("No relevant source chunks were found. Try ingesting more pages or asking a broader question.")

        names = self.extractor.candidate_names(question)
        for source in sources:
            names.extend(self.extractor.candidate_names(source.snippet))
        try:
            graph_context = await self.graph_store.query_context(names=list(dict.fromkeys(names)))
        except Exception:
            graph_context = []

        prompt = self._build_prompt(question, sources, graph_context)
        answer = await self.ollama.generate(prompt)
        return QueryResponse(answer=answer, sources=sources, graph_context=graph_context)

    async def _boost_sources(self, question: str, sources: list[RetrievedSource]) -> list[RetrievedSource]:
        lowered = question.lower()
        boosted: list[RetrievedSource] = []
        if any(term in lowered for term in ["course", "courses", "programme", "programmes", "program", "programs"]):
            boosted.extend(await self.vector_store.get_by_source_urls(COURSE_SOURCE_URLS, limit_per_url=2))

        combined = boosted + sources
        seen: set[tuple[str, str]] = set()
        deduped: list[RetrievedSource] = []
        for source in combined:
            key = (source.url, source.snippet[:80])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(source)
        return deduped[: max(self.settings.retrieval_top_k, 5)]

    def _build_prompt(
        self,
        question: str,
        sources: list[RetrievedSource],
        graph_context: list[dict],
    ) -> str:
        source_text = "\n\n".join(
            f"Source {index + 1}: {source.title}\nURL: {source.url}\nText: {source.snippet}"
            for index, source in enumerate(sources)
        )
        graph_text = "\n".join(
            f"{row['source_label']}({row['source']}) -[{row['relationship']}]- {row['target_label']}({row['target']})"
            for row in graph_context
        ) or "No SQLite graph relationships found."

        return f"""
You are a college website knowledge assistant for Sri Krishna College of Technology.
Use the supplied ChromaDB semantic context and SQLite graph relationship context to answer naturally.
Rules:
- Answer only from the supplied context.
- If the context is insufficient, say what is missing and suggest what page should be ingested.
- Be helpful, specific, and easy for a student or parent to understand.
- Mention source URLs briefly when useful.
- Do not invent faculty names, companies, numbers, dates, or events.

Question:
{question}

Semantic context:
{source_text}

Graph relationship context:
{graph_text}

Grounded answer:
""".strip()
