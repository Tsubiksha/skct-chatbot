from typing import Any

from pydantic import BaseModel, Field, HttpUrl

GraphEntityCounts = dict[str, int | str]


class SourceDocument(BaseModel):
    url: str
    title: str = "Untitled"
    text: str


class Chunk(BaseModel):
    id: str
    text: str
    source_url: str
    title: str
    chunk_index: int


class ScrapeRequest(BaseModel):
    base_url: HttpUrl | None = None
    max_pages: int | None = Field(default=None, ge=1, le=100)
    keywords: list[str] | None = None


class ScrapeResponse(BaseModel):
    pages_scraped: int
    documents: list[SourceDocument]


class IngestRequest(BaseModel):
    scrape_first: bool = True
    reset: bool = False
    max_pages: int | None = Field(default=None, ge=1, le=100)


class IngestResponse(BaseModel):
    documents: int
    chunks: int
    graph_entities: GraphEntityCounts
    message: str


class QueryRequest(BaseModel):
    question: str | None = Field(default=None)
    query: str | None = Field(default=None)
    top_k: int = Field(default=3, ge=1, le=5)


class RetrievedSource(BaseModel):
    title: str
    url: str
    snippet: str
    score: float | None = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[RetrievedSource]
    graph_context: list[dict[str, Any]]


class HealthResponse(BaseModel):
    status: str
    services: dict[str, str]


class GraphStatsResponse(BaseModel):
    departments: int = 0
    faculty: int = 0
    courses: int = 0
    companies: int = 0
    events: int = 0
    relationships: int = 0
    chunks: int = 0
