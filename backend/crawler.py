import asyncio
import aiohttp
import re
from urllib.parse import urljoin, urlparse, urldefrag
from bs4 import BeautifulSoup
from typing import List, Dict, Set, Tuple, Optional

USER_AGENT = "SKCTGraphRAGBot/2.0 Educational Project"
SKIP_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".css", ".js", ".mp4", ".avi", ".mov", ".pdf", ".zip", ".tar", ".gz")
SKIP_PATHS = ("login", "admin", "wp-admin", "wp-login", "cart", "checkout", "product", "wp-content")

class AsyncCrawler:
    def __init__(self, base_url: str = "https://skct.edu.in/", delay: float = 0.5):
        self.base_url = base_url
        self.base_host = urlparse(base_url).netloc.replace("www.", "")
        self.delay = delay
        self.visited: Set[str] = set()
        self.pages: List[Dict[str, str]] = []
        self.errors: List[str] = []

    def _normalize_url(self, url: str) -> Optional[str]:
        url, _ = urldefrag(url)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return None
        host = parsed.netloc.replace("www.", "")
        if host != self.base_host:
            return None
        return url.rstrip("/")

    def _should_skip(self, url: str) -> bool:
        lowered = url.lower()
        if lowered.endswith(SKIP_EXTENSIONS):
            return True
        if any(path in lowered for path in SKIP_PATHS):
            return True
        return False

    def _detect_page_type(self, url: str, title: str, content: str) -> str:
        haystack = f"{url} {title} {content[:2000]}".lower()
        checks = [
            ("placement", ["placement", "placements", "recruiter", "recruiters", "career", "hiring"]),
            ("department", ["department", "departments", "cse", "ece", "eee", "aids", "it", "civil", "mechanical"]),
            ("faculty", ["faculty", "professor", "hod", "principal", "staff", "teacher"]),
            ("academics", ["academics", "course", "curriculum", "syllabus", "regulation"]),
            ("event", ["event", "events", "seminar", "workshop", "conference", "symposium"]),
            ("contact", ["contact", "phone", "email", "address"]),
            ("research", ["research", "publication", "patent", "project"]),
        ]
        for ptype, keywords in checks:
            if any(kw in haystack for kw in keywords):
                return ptype
        return "general"

    def _clean_html(self, html: str) -> Tuple[str, str]:
        soup = BeautifulSoup(html, "lxml")
        
        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
            element.decompose()
            
        title = soup.title.string.strip() if soup.title and soup.title.string else "SKCT College Page"
        
        # Get raw text and merge whitespaces
        text = soup.get_text(separator="\n")
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase for phrase in lines if phrase)
        cleaned_text = "\n".join(chunks)
        
        return title, cleaned_text

    async def _fetch_and_parse(self, session: aiohttp.ClientSession, url: str) -> Tuple[Optional[Dict[str, str]], List[str]]:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        try:
            async with session.get(url, headers=headers, timeout=15) as response:
                if response.status != 200:
                    return None, []
                
                content_type = response.headers.get("Content-Type", "")
                if "text/html" not in content_type:
                    return None, []
                
                html = await response.text(errors="ignore")
                title, content = self._clean_html(html)
                
                # Extract links
                links = []
                soup = BeautifulSoup(html, "lxml")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    abs_url = urljoin(url, href)
                    norm_url = self._normalize_url(abs_url)
                    if norm_url and norm_url not in self.visited and not self._should_skip(norm_url):
                        links.append(norm_url)
                
                page_type = self._detect_page_type(url, title, content)
                
                page_data = {
                    "url": url,
                    "title": title,
                    "content": content,
                    "page_type": page_type
                }
                return page_data, links
        except Exception as e:
            self.errors.append(f"Error fetching {url}: {str(e)}")
            return None, []

    async def crawl(self, max_pages: int = 30, max_depth: int = 2) -> List[Dict[str, str]]:
        self.visited.clear()
        self.pages.clear()
        self.errors.clear()
        
        queue = [(self.base_url, 0)]
        self.visited.add(self._normalize_url(self.base_url))
        
        async with aiohttp.ClientSession() as session:
            while queue and len(self.pages) < max_pages:
                # Process a batch of links to maintain high throughput while keeping concurrency controlled
                current_batch = []
                while queue and len(current_batch) < 5:
                    current_batch.append(queue.pop(0))
                
                tasks = [self._fetch_and_parse(session, url) for url, depth in current_batch]
                results = await asyncio.gather(*tasks)
                
                for (url, depth), res in zip(current_batch, results):
                    page_data, links = res
                    if page_data:
                        self.pages.append(page_data)
                        
                    # Queue links if depth limit is not reached
                    if depth < max_depth:
                        for link in links:
                            normalized_link = self._normalize_url(link)
                            if normalized_link and normalized_link not in self.visited:
                                self.visited.add(normalized_link)
                                queue.append((normalized_link, depth + 1))
                                
                await asyncio.sleep(self.delay)
                
        return self.pages[:max_pages]
