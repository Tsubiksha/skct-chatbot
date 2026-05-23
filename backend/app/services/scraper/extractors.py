import io
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from pypdf import PdfReader
from backend.app.schemas.document import ParsedDocument

class WebExtractor:
    @staticmethod
    def extract_html(url: str, html_content: str, depth: int) -> ParsedDocument:
        soup = BeautifulSoup(html_content, "lxml")
        
        # Remove scripts, styles
        for element in soup(["script", "style", "nav", "footer"]):
            element.decompose()
            
        title = soup.title.string if soup.title else "Unknown Title"
        
        headings = []
        for h in soup.find_all(['h1', 'h2', 'h3']):
            if h.text.strip():
                headings.append(h.text.strip())
                
        links = []
        for a in soup.find_all('a', href=True):
            links.append(urljoin(url, a['href']))
            
        # Extract tables
        tables_data = []
        for table in soup.find_all('table'):
            t_data = []
            for row in table.find_all('tr'):
                cols = [ele.text.strip() for ele in row.find_all(['td', 'th'])]
                if any(cols):
                    t_data.append(cols)
            if t_data:
                tables_data.append(t_data)
                
        # Basic text extraction
        raw_text = soup.get_text(separator="\n", strip=True)
        
        # Determine department heuristically based on URL or title
        department = "General"
        url_lower = url.lower()
        if "cse" in url_lower or "computer-science" in url_lower:
            department = "CSE"
        elif "it" in url_lower or "information-technology" in url_lower:
            department = "IT"
        elif "ece" in url_lower:
            department = "ECE"
        elif "eee" in url_lower:
            department = "EEE"
        elif "mech" in url_lower or "mechanical" in url_lower:
            department = "MECH"
        elif "civil" in url_lower:
            department = "CIVIL"
        elif "ai-ds" in url_lower or "aids" in url_lower or "artificial" in url_lower:
            department = "AI-DS"
            
        return ParsedDocument(
            url=url,
            title=title.strip(),
            content_type="html",
            raw_text=raw_text,
            headings=headings,
            links=links,
            tables_data=tables_data,
            metadata={
                "source": url,
                "depth": depth,
                "department": department
            }
        )

    @staticmethod
    def extract_pdf(url: str, pdf_bytes: bytes, depth: int) -> ParsedDocument:
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
                
            return ParsedDocument(
                url=url,
                title=url.split("/")[-1],
                content_type="pdf",
                raw_text=text.strip(),
                metadata={
                    "source": url,
                    "depth": depth,
                    "department": "General" # Might be enhanced later
                }
            )
        except Exception as e:
            print(f"Failed to parse PDF {url}: {e}")
            return None
