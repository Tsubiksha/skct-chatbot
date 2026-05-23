import re
import uuid
from typing import List, Dict, Any

class SemanticChunker:
    def __init__(self, chunk_size: int = 1500, overlap: int = 250):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split_into_sentences(self, text: str) -> List[str]:
        # Split sentences preserving common abbreviations like Dr., Prof., B.E., B.Tech., M.E.
        sentence_end = re.compile(r'(?<!\bDr)(?<!\bProf)(?<!\bMr)(?<!\bMs)(?<!\bMrs)(?<!\bB\.E)(?<!\bM\.E)(?<!\bB\.Tech)(?<!\bM\.Tech)(?<!\bPh\.D)\.\s+|[!?]\s+')
        sentences = sentence_end.split(text)
        # Re-attach split punctuation if needed, or simply return trimmed list
        return [s.strip() for s in sentences if s.strip()]

    def extract_department(self, text: str, title: str) -> str:
        # Detect matching department names to inject into metadata
        haystack = f"{title} {text[:500]}".lower()
        depts = {
            "Computer Science and Engineering": ["cse", "computer science", "computer engineering"],
            "Artificial Intelligence and Data Science": ["aids", "ai & ds", "ai and ds", "artificial intelligence"],
            "Electronics and Communication Engineering": ["ece", "electronics and communication"],
            "Electrical and Electronics Engineering": ["eee", "electrical and electronics"],
            "Information Technology": ["it", "information technology"],
            "Civil Engineering": ["civil engineering", "civil"],
            "Mechanical Engineering": ["mechanical engineering", "mechanical"],
        }
        for full_name, keywords in depts.items():
            if any(kw in haystack for kw in keywords):
                return full_name
        return "General"

    def chunk_page(self, page: Dict[str, str]) -> List[Dict[str, Any]]:
        url = page.get("url", "")
        title = page.get("title", "")
        content = page.get("content", "")
        page_type = page.get("page_type", "general")
        
        paragraphs = content.split("\n\n")
        chunks: List[Dict[str, Any]] = []
        
        current_chunk_text = ""
        current_heading = "Introduction"
        chunk_idx = 0
        
        department = self.extract_department(content, title)
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
                
            # If paragraph looks like a heading, update active heading
            if len(para) < 120 and (para.startswith("#") or para.isupper() or any(keyword in para.lower() for keyword in ["department of", "faculty details", "placement highlights", "courses offered", "contact us"])):
                current_heading = para.replace("#", "").strip()
                
            # Check size of adding paragraph
            if len(current_chunk_text) + len(para) <= self.chunk_size:
                current_chunk_text += "\n\n" + para if current_chunk_text else para
            else:
                # If current chunk has text, save it
                if current_chunk_text.strip():
                    chunk_text = f"Page: {title}\nSection: {current_heading}\n\n{current_chunk_text.strip()}"
                    chunk_id = f"{uuid.uuid5(uuid.NAMESPACE_URL, url)}_{chunk_idx}"
                    chunks.append({
                        "id": chunk_id,
                        "chunk_text": chunk_text,
                        "url": url,
                        "title": title,
                        "page_type": page_type,
                        "chunk_index": chunk_idx,
                        "department": department
                    })
                    chunk_idx += 1
                
                # If paragraph itself is too large, split it into sentences
                if len(para) > self.chunk_size:
                    sentences = self.split_into_sentences(para)
                    current_chunk_text = ""
                    for sent in sentences:
                        if len(current_chunk_text) + len(sent) <= self.chunk_size:
                            current_chunk_text += " " + sent if current_chunk_text else sent
                        else:
                            if current_chunk_text.strip():
                                chunk_text = f"Page: {title}\nSection: {current_heading}\n\n{current_chunk_text.strip()}"
                                chunk_id = f"{uuid.uuid5(uuid.NAMESPACE_URL, url)}_{chunk_idx}"
                                chunks.append({
                                    "id": chunk_id,
                                    "chunk_text": chunk_text,
                                    "url": url,
                                    "title": title,
                                    "page_type": page_type,
                                    "chunk_index": chunk_idx,
                                    "department": department
                                })
                                chunk_idx += 1
                            current_chunk_text = sent
                else:
                    # Initialize next chunk text with overlap if possible
                    overlap_text = current_chunk_text[-self.overlap:] if len(current_chunk_text) > self.overlap else ""
                    current_chunk_text = (overlap_text + "\n\n" + para).strip()
                    
        # Flush final chunk
        if current_chunk_text.strip():
            chunk_text = f"Page: {title}\nSection: {current_heading}\n\n{current_chunk_text.strip()}"
            chunk_id = f"{uuid.uuid5(uuid.NAMESPACE_URL, url)}_{chunk_idx}"
            chunks.append({
                "id": chunk_id,
                "chunk_text": chunk_text,
                "url": url,
                "title": title,
                "page_type": page_type,
                "chunk_index": chunk_idx,
                "department": department
            })
            
        return chunks
