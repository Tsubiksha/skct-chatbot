from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    frontend_origin: str = "http://localhost:5173"

    college_base_url: str = "https://skct.edu.in/"
    max_scrape_pages: int = 20
    chunk_size: int = 500
    chunk_overlap: int = 80
    retrieval_top_k: int = 3
    auto_ingest_on_startup: bool = True
    auto_ingest_max_pages: int = 3
    sqlite_auto_ingest_max_pages: int = 8

    ollama_base_url: str = "http://localhost:11434"
    ollama_llm_model: str = "llama3:8b"
    ollama_embed_model: str = "nomic-embed-text"

    chroma_path: str = "./data/chroma"
    chroma_collection: str = "college_knowledge"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = Field(default="password", repr=False)
    neo4j_database: str = "neo4j"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
