"""
chunker.py — Heading-aware semantic chunker for SKCT Graph RAG.

Improvements over v1:
  - Splits on heading boundaries FIRST, then word count
  - Prefixes every chunk with [PageTitle > Section] for better FTS matching
  - Smaller default chunk size (250 words) for higher retrieval precision
  - Smaller overlap (40 words)
  - Skips chunks with < 20 meaningful words
  - Stores heading breadcrumb in chunk for context
"""

import re
import logging
from backend.app.graph_sqlite.db import get_conn

logger = logging.getLogger(__name__)

# ── Tunable constants ─────────────────────────────────────────────────────────
CHUNK_SIZE      = 250   # target words per chunk (smaller → more precise retrieval)
CHUNK_OVERLAP   = 40    # overlap words between consecutive chunks
MIN_CHUNK_WORDS = 20    # drop tiny/uninformative chunks

# Regex to detect heading markers injected by text_cleaner
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")


# ── Public API ────────────────────────────────────────────────────────────────

def chunk_and_store(page_id: int, url: str, title: str, page_type: str,
                    content: str) -> int:
    """
    Split content into heading-aware semantic chunks.
    Stores in website_chunks + website_chunks_fts (FTS5).
    Deletes existing chunks for this page_id first.
    Returns number of chunks stored.
    """
    chunks = _build_heading_aware_chunks(title, content)

    if not chunks:
        return 0

    conn = get_conn()
    try:
        # Remove old chunks for this page
        old_ids = [
            row[0] for row in
            conn.execute("SELECT id FROM website_chunks WHERE page_id=?", (page_id,)).fetchall()
        ]
        if old_ids:
            placeholders = ",".join("?" * len(old_ids))
            try:
                conn.execute(
                    f"DELETE FROM website_chunks_fts WHERE rowid IN ({placeholders})",
                    old_ids
                )
            except Exception:
                pass
            conn.execute(
                f"DELETE FROM website_chunks WHERE id IN ({placeholders})",
                old_ids
            )

        # Insert new chunks
        for idx, chunk_text in enumerate(chunks):
            cur = conn.execute(
                """INSERT INTO website_chunks
                     (page_id, url, title, page_type, chunk_text, chunk_index, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                (page_id, url, title, page_type, chunk_text, idx),
            )
            row_id = cur.lastrowid
            try:
                conn.execute(
                    "INSERT INTO website_chunks_fts "
                    "(rowid, title, url, page_type, chunk_text) VALUES (?,?,?,?,?)",
                    (row_id, title, url, page_type, chunk_text),
                )
            except Exception as e:
                logger.debug(f"FTS insert skipped for chunk {row_id}: {e}")

        conn.commit()
        logger.debug(
            f"[Chunker] {len(chunks)} chunks stored for page_id={page_id} "
            f"url={url} page_type={page_type}"
        )
        return len(chunks)

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rebuild_fts() -> int:
    """Rebuild the FTS5 index from scratch from website_chunks table."""
    conn = get_conn()
    try:
        try:
            conn.execute("DELETE FROM website_chunks_fts")
        except Exception as e:
            logger.warning(f"[Chunker] FTS table reset required: {e}")
            conn.execute("DROP TABLE IF EXISTS website_chunks_fts")
            conn.execute(
                """CREATE VIRTUAL TABLE website_chunks_fts
                   USING fts5(title, url, page_type, chunk_text,
                              content='website_chunks', content_rowid='id')"""
            )
        rows = conn.execute(
            "SELECT id, title, url, page_type, chunk_text FROM website_chunks"
        ).fetchall()
        for row in rows:
            conn.execute(
                "INSERT INTO website_chunks_fts "
                "(rowid, title, url, page_type, chunk_text) VALUES (?,?,?,?,?)",
                (row["id"], row["title"], row["url"], row["page_type"], row["chunk_text"]),
            )
        conn.commit()
        logger.info(f"[Chunker] FTS rebuilt: {len(rows)} chunks indexed")
        return len(rows)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Internal chunking logic ───────────────────────────────────────────────────

def _build_heading_aware_chunks(page_title: str, content: str) -> list[str]:
    """
    Split content into heading-aware chunks.
    Each chunk is prefixed with [PageTitle > Section Heading] context.
    """
    # Parse into sections delimited by headings
    sections = _split_into_sections(content)

    all_chunks: list[str] = []

    for section_heading, section_body in sections:
        # Build context prefix for this section
        if section_heading:
            context_prefix = f"[{page_title} > {section_heading}]\n"
        else:
            context_prefix = f"[{page_title}]\n"

        # Further split section body by word count
        word_chunks = _split_by_word_count(
            section_body,
            chunk_size=CHUNK_SIZE,
            overlap=CHUNK_OVERLAP
        )

        for chunk_text in word_chunks:
            # Clean up the chunk
            chunk_text = _clean_chunk(chunk_text)
            words = chunk_text.split()
            if len(words) < MIN_CHUNK_WORDS:
                continue

            # Prepend the context prefix
            final_chunk = context_prefix + chunk_text
            all_chunks.append(final_chunk)

    return all_chunks


def _split_into_sections(content: str) -> list[tuple[str, str]]:
    """
    Split content into (heading, body) pairs using heading markers from text_cleaner.
    Returns list of (heading_text, body_text) tuples.
    First section may have empty heading (content before first heading).
    """
    lines = content.splitlines()
    sections: list[tuple[str, str]] = []

    current_heading = ""
    current_body: list[str] = []

    for line in lines:
        m = _HEADING_RE.match(line.strip())
        if m:
            # Save previous section
            body = "\n".join(current_body).strip()
            if body or current_heading:
                sections.append((current_heading, body))
            # Start new section
            current_heading = m.group(2).strip()
            current_body = []
        else:
            current_body.append(line)

    # Flush last section
    body = "\n".join(current_body).strip()
    if body or current_heading:
        sections.append((current_heading, body))

    # If no headings found at all, return the whole content as one section
    if not sections:
        return [("", content.strip())]

    return sections


def _split_by_word_count(text: str, chunk_size: int, overlap: int) -> list[str]:
    """
    Split text into overlapping word-count-capped chunks.
    Tries to split at sentence boundaries.
    """
    if not text.strip():
        return []

    sentences = _split_sentences(text)
    chunks: list[str] = []
    current_words: list[str] = []
    current_len = 0

    for sentence in sentences:
        words = sentence.split()
        if not words:
            continue

        # Single sentence bigger than chunk_size → hard split
        if len(words) > chunk_size:
            if current_words and current_len >= MIN_CHUNK_WORDS:
                chunks.append(" ".join(current_words))
            for i in range(0, len(words), chunk_size - overlap):
                seg = words[i: i + chunk_size]
                if len(seg) >= MIN_CHUNK_WORDS:
                    chunks.append(" ".join(seg))
            current_words = words[-overlap:] if len(words) > overlap else words[:]
            current_len = len(current_words)
            continue

        # Would adding this sentence exceed chunk_size?
        if current_len + len(words) > chunk_size and current_len >= MIN_CHUNK_WORDS:
            chunks.append(" ".join(current_words))
            overlap_words = current_words[-overlap:] if len(current_words) > overlap else current_words[:]
            current_words = overlap_words + words
            current_len = len(current_words)
        else:
            current_words.extend(words)
            current_len += len(words)

    # Flush remainder
    if current_len >= MIN_CHUNK_WORDS:
        chunks.append(" ".join(current_words))

    return chunks


def _split_sentences(text: str) -> list[str]:
    """
    Split on sentence boundaries and blank lines, preserving table rows.
    """
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Split on sentence-ending punctuation followed by whitespace, or blank lines
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", text)
    result = []
    for p in parts:
        p = p.strip()
        if p:
            result.append(p)
    return result


def _clean_chunk(text: str) -> str:
    """Light normalization of a chunk before storing."""
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
