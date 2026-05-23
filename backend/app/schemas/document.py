from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class DocumentChunk(BaseModel):
    chunk_id: str
    content: str
    metadata: Dict[str, str | int | float | bool]

class ParsedDocument(BaseModel):
    url: str
    title: str
    content_type: str # "html", "pdf"
    raw_text: str
    headings: List[str] = Field(default_factory=list)
    links: List[str] = Field(default_factory=list)
    metadata: Dict[str, str | int | float | bool] = Field(default_factory=dict)
    
    # Specific extraction fields
    faculty_members: List[Dict[str, str]] = Field(default_factory=list)
    tables_data: List[List[List[str]]] = Field(default_factory=list)
