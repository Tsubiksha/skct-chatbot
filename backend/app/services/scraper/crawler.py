import asyncio
import aiohttp
from urllib.parse import urlparse, urljoin
from typing import List, Set
from backend.app.config import settings
from backend.app.schemas.document import ParsedDocument
from backend.app.services.scraper.extractors import WebExtractor

class AsyncCrawler:
    def __init__(self, base_url: str = settings.BASE_URL, max_depth: int = settings.MAX_CRAWL_DEPTH):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        self.max_depth = max_depth
        self.visited: Set[str] = set()
        self.documents: List[ParsedDocument] = []
        
    async def fetch(self, session: aiohttp.ClientSession, url: str) -> tuple[bytes, str]:
        try:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    content_type = response.headers.get('Content-Type', '')
                    return await response.read(), content_type
        except Exception as e:
            print(f"Error fetching {url}: {e}")
        return b"", ""

    def is_valid_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return parsed.netloc == self.domain and url not in self.visited

    async def crawl_recursive(self, session: aiohttp.ClientSession, current_url: str, depth: int):
        if depth > self.max_depth or current_url in self.visited:
            return

        self.visited.add(current_url)
        print(f"Crawling (Depth {depth}): {current_url}")
        
        content, content_type = await self.fetch(session, current_url)
        if not content:
            return

        doc = None
        if 'application/pdf' in content_type:
            doc = WebExtractor.extract_pdf(current_url, content, depth)
        elif 'text/html' in content_type:
            # Decode HTML
            try:
                html_text = content.decode('utf-8')
            except UnicodeDecodeError:
                html_text = content.decode('latin-1', errors='ignore')
            
            doc = WebExtractor.extract_html(current_url, html_text, depth)
            
        if doc:
            self.documents.append(doc)
            
            # Recurse for HTML links
            if doc.content_type == "html" and depth < self.max_depth:
                tasks = []
                for link in doc.links:
                    # Clean up link (remove fragments)
                    clean_link = link.split('#')[0]
                    if self.is_valid_url(clean_link):
                        tasks.append(self.crawl_recursive(session, clean_link, depth + 1))
                
                # Rate limit concurrent tasks if necessary
                if tasks:
                    await asyncio.gather(*tasks)
                    await asyncio.sleep(settings.CRAWL_DELAY)

    async def run(self) -> List[ParsedDocument]:
        async with aiohttp.ClientSession() as session:
            await self.crawl_recursive(session, self.base_url, 0)
        return self.documents
