from dataclasses import dataclass


@dataclass
class TextChunk:
    chunk_text: str
    chunk_index: int


def chunk_text(text: str, chunk_size: int = 850, overlap: int = 100) -> list[TextChunk]:
    words = text.split()
    if not words:
        return []

    chunks: list[TextChunk] = []
    step = max(1, chunk_size - overlap)
    for index, start in enumerate(range(0, len(words), step)):
        chunk_words = words[start : start + chunk_size]
        if len(chunk_words) < 40 and start > 0:
            continue
        chunks.append(TextChunk(chunk_text=" ".join(chunk_words), chunk_index=index))
    return chunks
