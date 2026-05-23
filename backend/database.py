import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "graph_rag.db"

def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DB_PATH))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    return connection

def init_db() -> None:
    """Initialize SQLite database with all tables and triggers."""
    with get_connection() as conn:
        # Users Table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        
        # Conversations Table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)
        
        # Messages Table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL, -- 'user' or 'assistant'
            content TEXT NOT NULL,
            sources TEXT, -- JSON string containing page citations
            graph_context TEXT, -- JSON string containing graph relationships
            created_at TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
        """)
        
        # Scraped Pages Table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS scraped_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            page_type TEXT NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            scraped_at TEXT NOT NULL
        )
        """)
        
        # Website Chunks Table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS website_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            page_type TEXT NOT NULL,
            chunk_text TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(page_id) REFERENCES scraped_pages(id) ON DELETE CASCADE
        )
        """)
        
        # FTS5 Virtual Table for Website Chunks
        conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS website_chunks_fts USING fts5(
            title,
            url UNINDEXED,
            page_type,
            chunk_text,
            content='website_chunks',
            content_rowid='id'
        )
        """)
        
        # Entities Table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            name TEXT NOT NULL,
            page_id INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(entity_type, name, page_id),
            FOREIGN KEY(page_id) REFERENCES scraped_pages(id) ON DELETE CASCADE
        )
        """)
        
        # Relationships Table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_name TEXT NOT NULL,
            relationship_type TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_name TEXT NOT NULL,
            page_id INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(source_type, source_name, relationship_type, target_type, target_name, page_id),
            FOREIGN KEY(page_id) REFERENCES scraped_pages(id) ON DELETE CASCADE
        )
        """)
        
        # Ingestion Logs Table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL,
            message TEXT NOT NULL,
            pages_visited INTEGER DEFAULT 0,
            pages_saved INTEGER DEFAULT 0,
            pages_updated INTEGER DEFAULT 0,
            chunks_created INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """)
        
        # Triggers for keeping FTS5 index synchronized
        conn.execute("""
        CREATE TRIGGER IF NOT EXISTS website_chunks_ai AFTER INSERT ON website_chunks BEGIN
            INSERT INTO website_chunks_fts(rowid, title, url, page_type, chunk_text)
            VALUES (new.id, new.title, new.url, new.page_type, new.chunk_text);
        END;
        """)
        
        # Trigger on Delete
        conn.execute("""
        CREATE TRIGGER IF NOT EXISTS website_chunks_ad AFTER DELETE ON website_chunks BEGIN
            INSERT INTO website_chunks_fts(website_chunks_fts, rowid, title, url, page_type, chunk_text)
            VALUES ('delete', old.id, old.title, old.url, old.page_type, old.chunk_text);
        END;
        """)
        
        # Trigger on Update
        conn.execute("""
        CREATE TRIGGER IF NOT EXISTS website_chunks_au AFTER UPDATE ON website_chunks BEGIN
            INSERT INTO website_chunks_fts(website_chunks_fts, rowid, title, url, page_type, chunk_text)
            VALUES ('delete', old.id, old.title, old.url, old.page_type, old.chunk_text);
            INSERT INTO website_chunks_fts(rowid, title, url, page_type, chunk_text)
            VALUES (new.id, new.title, new.url, new.page_type, new.chunk_text);
        END;
        """)
        
        conn.commit()

# --- Auth DB Helpers ---

def create_user(username: str, email: str, hashed_password: str) -> int:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO users (username, email, hashed_password, created_at) VALUES (?, ?, ?, ?)",
            (username, email, hashed_password, now)
        )
        conn.commit()
        return cursor.lastrowid

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

# --- Chat DB Helpers ---

def create_conversation(user_id: int, title: str) -> int:
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO conversations (user_id, title, created_at) VALUES (?, ?, ?)",
            (user_id, title, now)
        )
        conn.commit()
        return cursor.lastrowid

def get_conversations_by_user(user_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()
        return [dict(row) for row in rows]

def get_conversation(conv_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
            (conv_id, user_id)
        ).fetchone()
        return dict(row) if row else None

def delete_conversation(conv_id: int, user_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (conv_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0

def add_message(conv_id: int, role: str, content: str, sources: Optional[List[Dict[str, Any]]] = None, graph_context: Optional[List[Dict[str, Any]]] = None) -> int:
    now = datetime.utcnow().isoformat()
    sources_json = json.dumps(sources) if sources else None
    graph_json = json.dumps(graph_context) if graph_context else None
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO messages (conversation_id, role, content, sources, graph_context, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (conv_id, role, content, sources_json, graph_json, now)
        )
        conn.commit()
        return cursor.lastrowid

def get_messages(conv_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (conv_id,)
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["sources"] = json.loads(d["sources"]) if d["sources"] else []
            d["graph_context"] = json.loads(d["graph_context"]) if d["graph_context"] else []
            result.append(d)
        return result
