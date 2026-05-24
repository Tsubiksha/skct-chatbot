-- Graph RAG SQLite Schema
-- Isolated database: backend/data/graph_rag.db
-- NEVER touches the existing Supabase / app database

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ============================================================
-- 1. students
-- ============================================================
CREATE TABLE IF NOT EXISTS students (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    register_no         TEXT UNIQUE NOT NULL,
    name                TEXT,
    department          TEXT,
    section             TEXT,
    batch               TEXT,
    branch              TEXT,
    college_email       TEXT,
    personal_email      TEXT,
    contact_number      TEXT,
    dob                 TEXT,
    gender              TEXT,
    tenth_percent       TEXT,
    twelfth_percent     TEXT,
    ug_cgpa             REAL,
    arrears_count       TEXT,
    history_of_arrears  TEXT,
    gap_in_education    TEXT,
    source_file         TEXT,
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 2. semesters
-- ============================================================
CREATE TABLE IF NOT EXISTS semesters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    semester_no INTEGER UNIQUE
);

-- ============================================================
-- 3. subjects
-- ============================================================
CREATE TABLE IF NOT EXISTS subjects (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_code TEXT,
    subject_name TEXT,
    semester_no  INTEGER,
    department   TEXT,
    source_file  TEXT,
    UNIQUE(subject_code, subject_name, semester_no)
);

-- ============================================================
-- 4. results
-- ============================================================
CREATE TABLE IF NOT EXISTS results (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    register_no    TEXT NOT NULL,
    student_name   TEXT,
    semester_no    INTEGER,
    subject_code   TEXT,
    subject_name   TEXT,
    grade          TEXT,
    grade_points   REAL,
    result_status  TEXT,
    gpa            REAL,
    cgpa           REAL,
    source_file    TEXT,
    source_sheet   TEXT,
    row_number     INTEGER,
    created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(register_no, semester_no, subject_code, subject_name, source_sheet),
    FOREIGN KEY(register_no) REFERENCES students(register_no)
);

-- ============================================================
-- 5. scraped_pages
-- ============================================================
CREATE TABLE IF NOT EXISTS scraped_pages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url          TEXT UNIQUE,
    title        TEXT,
    page_type    TEXT,
    content      TEXT,
    content_hash TEXT,
    scraped_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 6. website_chunks
-- ============================================================
CREATE TABLE IF NOT EXISTS website_chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id     INTEGER,
    url         TEXT,
    title       TEXT,
    page_type   TEXT,
    chunk_text  TEXT,
    chunk_index INTEGER,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(page_id) REFERENCES scraped_pages(id)
);

-- ============================================================
-- 7. page_links
-- ============================================================
CREATE TABLE IF NOT EXISTS page_links (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source_page_id INTEGER,
    source_url     TEXT,
    target_url     TEXT,
    link_text      TEXT,
    depth          INTEGER,
    created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_url, target_url),
    FOREIGN KEY(source_page_id) REFERENCES scraped_pages(id)
);

-- ============================================================
-- 8. website_chunks_fts (FTS5 virtual table)
-- ============================================================
CREATE VIRTUAL TABLE IF NOT EXISTS website_chunks_fts
USING fts5(title, url, page_type, chunk_text,
           content='website_chunks', content_rowid='id');

-- ============================================================
-- 9. entities
-- ============================================================
CREATE TABLE IF NOT EXISTS entities (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    entity_type   TEXT NOT NULL,
    source_type   TEXT,
    source_id     INTEGER,
    metadata_json TEXT,
    UNIQUE(name, entity_type)
);

-- ============================================================
-- 10. relationships
-- ============================================================
CREATE TABLE IF NOT EXISTS relationships (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_entity_id  INTEGER NOT NULL,
    relation_type     TEXT NOT NULL,
    target_entity_id  INTEGER NOT NULL,
    properties_json   TEXT,
    UNIQUE(source_entity_id, relation_type, target_entity_id, properties_json),
    FOREIGN KEY(source_entity_id) REFERENCES entities(id),
    FOREIGN KEY(target_entity_id) REFERENCES entities(id)
);

-- ============================================================
-- 11. ingestion_logs
-- ============================================================
CREATE TABLE IF NOT EXISTS ingestion_logs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type    TEXT,
    source_name    TEXT,
    status         TEXT,
    message        TEXT,
    rows_read      INTEGER DEFAULT 0,
    rows_inserted  INTEGER DEFAULT 0,
    rows_skipped   INTEGER DEFAULT 0,
    created_at     TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 12. graph_chat_sessions
-- ============================================================
CREATE TABLE IF NOT EXISTS graph_chat_sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT,
    title      TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 13. graph_chat_messages
-- ============================================================
CREATE TABLE IF NOT EXISTS graph_chat_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER,
    user_id      TEXT,
    role         TEXT,
    content      TEXT,
    context_json TEXT,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(session_id) REFERENCES graph_chat_sessions(id)
);
