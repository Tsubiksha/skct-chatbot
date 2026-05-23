PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS scraped_pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    page_type TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    scraped_at TEXT NOT NULL
);

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
);

CREATE VIRTUAL TABLE IF NOT EXISTS website_chunks_fts USING fts5(
    title,
    url UNINDEXED,
    page_type,
    chunk_text,
    content='website_chunks',
    content_rowid='id'
);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    page_id INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(entity_type, name, page_id),
    FOREIGN KEY(page_id) REFERENCES scraped_pages(id) ON DELETE CASCADE
);

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
);

CREATE TABLE IF NOT EXISTS ingestion_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    pages_visited INTEGER DEFAULT 0,
    pages_saved INTEGER DEFAULT 0,
    pages_updated INTEGER DEFAULT 0,
    chunks_created INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS website_chunks_ai AFTER INSERT ON website_chunks BEGIN
    INSERT INTO website_chunks_fts(rowid, title, url, page_type, chunk_text)
    VALUES (new.id, new.title, new.url, new.page_type, new.chunk_text);
END;

CREATE TRIGGER IF NOT EXISTS website_chunks_ad AFTER DELETE ON website_chunks BEGIN
    INSERT INTO website_chunks_fts(website_chunks_fts, rowid, title, url, page_type, chunk_text)
    VALUES ('delete', old.id, old.title, old.url, old.page_type, old.chunk_text);
END;

CREATE TRIGGER IF NOT EXISTS website_chunks_au AFTER UPDATE ON website_chunks BEGIN
    INSERT INTO website_chunks_fts(website_chunks_fts, rowid, title, url, page_type, chunk_text)
    VALUES ('delete', old.id, old.title, old.url, old.page_type, old.chunk_text);
    INSERT INTO website_chunks_fts(rowid, title, url, page_type, chunk_text)
    VALUES (new.id, new.title, new.url, new.page_type, new.chunk_text);
END;
