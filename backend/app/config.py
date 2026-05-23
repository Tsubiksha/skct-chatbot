from pydantic_settings import BaseSettings
import os
from pathlib import Path

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "SKCT College AI Assistant"
    VERSION: str = "2.0.0"
    
    # Paths
    DATA_DIR: Path = BASE_DIR / "backend" / "data"
    DB_DIR: Path = DATA_DIR
    CHROMA_DB_DIR: Path = DATA_DIR / "chroma"
    GRAPH_DB_PATH: Path = DATA_DIR / "graph_rag.db"
    RAW_HTML_DIR: Path = DATA_DIR / "raw_html"
    
    # Models
    LLM_MODEL: str = "llama3.2:3b"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    
    # Scraping
    BASE_URL: str = "https://skct.edu.in/"
    MAX_CRAWL_DEPTH: int = 5
    CRAWL_DELAY: float = 1.0 # seconds
    
    # Chunking
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# Ensure directories exist
os.makedirs(settings.DATA_DIR, exist_ok=True)
os.makedirs(settings.DB_DIR, exist_ok=True)
os.makedirs(settings.CHROMA_DB_DIR, exist_ok=True)
os.makedirs(settings.RAW_HTML_DIR, exist_ok=True)
