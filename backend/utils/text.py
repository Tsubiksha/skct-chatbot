import hashlib
import re
from urllib.parse import urlparse

from backend.models import Chunk, SourceDocument


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(\|){2,}", "|", text)
    return text.strip()


def stable_id(*parts: str) -> str:
    raw = "::".join(parts).encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()[:24]


def friendly_title_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return "Home"
    return path.split("/")[-1].replace("-", " ").replace("_", " ").title()


def chunk_documents(
    documents: list[SourceDocument],
    chunk_size: int,
    overlap: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    step = max(1, chunk_size - overlap)

    for document in documents:
        words = document.text.split()
        if not words:
            continue

        for index, start in enumerate(range(0, len(words), step)):
            chunk_words = words[start : start + chunk_size]
            if len(chunk_words) < 30 and start > 0:
                continue

            text = " ".join(chunk_words)
            chunks.append(
                Chunk(
                    id=stable_id(document.url, str(index), text[:80]),
                    text=text,
                    source_url=document.url,
                    title=document.title,
                    chunk_index=index,
                )
            )

    return chunks
