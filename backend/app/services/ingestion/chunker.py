import uuid
from typing import List
from backend.app.schemas.document import ParsedDocument, DocumentChunk
from backend.app.config import settings

class DocumentChunker:
    def __init__(self, chunk_size: int = settings.CHUNK_SIZE, overlap: int = settings.CHUNK_OVERLAP):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_document(self, doc: ParsedDocument) -> List[DocumentChunk]:
        chunks = []
        text = doc.raw_text
        
        # Simple overlap chunking
        # A more advanced version would use Langchain's RecursiveCharacterTextSplitter 
        # or NLTK sentence tokenization, but we implement a robust manual one here.
        
        start = 0
        text_length = len(text)
        chunk_index = 0
        
        while start < text_length:
            end = start + self.chunk_size
            
            # If we're not at the end of the text, try to find a natural break (newline or space)
            if end < text_length:
                # Look backwards for a newline
                last_newline = text.rfind('\n', start, end)
                if last_newline != -1 and last_newline > start + (self.chunk_size // 2):
                    end = last_newline + 1
                else:
                    # Look backwards for a space
                    last_space = text.rfind(' ', start, end)
                    if last_space != -1 and last_space > start + (self.chunk_size // 2):
                        end = last_space + 1
            
            chunk_text = text[start:end].strip()
            
            if chunk_text:
                # Build rich metadata for this chunk
                chunk_metadata = {
                    "url": doc.url,
                    "title": doc.title,
                    "content_type": doc.content_type,
                    "department": doc.metadata.get("department", "General"),
                    "depth": doc.metadata.get("depth", 0),
                    "chunk_index": chunk_index,
                    # Add nearest heading context if available (simplification: we just inject all headings as context)
                    "headings": " | ".join(doc.headings[:3]) if doc.headings else ""
                }
                
                chunks.append(DocumentChunk(
                    chunk_id=f"{uuid.uuid5(uuid.NAMESPACE_URL, doc.url)}_{chunk_index}",
                    content=f"Title: {doc.title}\nDepartment: {chunk_metadata['department']}\n\n{chunk_text}",
                    metadata=chunk_metadata
                ))
                chunk_index += 1
            
            # Move start forward, accounting for overlap
            start = end - self.overlap
            if start < 0:
                start = 0
                
            # Prevent infinite loop if we somehow don't advance
            if start == end:
                start += self.chunk_size

        return chunks
