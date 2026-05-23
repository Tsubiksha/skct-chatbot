import asyncio
import re
from collections import deque
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from backend.models import SourceDocument
from backend.scraper.pdf_loader import extract_pdf_text
from backend.utils.text import clean_text, friendly_title_from_url


DEFAULT_KEYWORDS = [
    "department",
    "faculty",
    "placement",
    "course",
    "event",
    "research",
    "academics",
]

SEED_PATHS = [
    "/",
    "/departments/",
    "/placement/",
    "/placements/",
    "/academics/",
    "/research/",
    "/events/",
    "/faculty/",
]


class CollegeScraper:
    def __init__(self, base_url: str, max_pages: int, keywords: list[str] | None = None):
        self.base_url = str(base_url)
        self.max_pages = max_pages
        self.keywords = [item.lower() for item in (keywords or DEFAULT_KEYWORDS)]
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    async def scrape(self) -> list[SourceDocument]:
        return await asyncio.to_thread(self._scrape_sync)

    def _scrape_sync(self) -> list[SourceDocument]:
        base_host = urlparse(self.base_url).netloc
        queue: deque[str] = deque(self._seed_urls())
        visited: set[str] = set()
        documents: list[SourceDocument] = []

        while queue and len(documents) < self.max_pages:
            url = self._normalize_url(queue.popleft())
            if not url or url in visited:
                continue

            visited.add(url)
            try:
                if url.lower().endswith(".pdf"):
                    text = extract_pdf_text(url)
                    documents.append(
                        SourceDocument(url=url, title=friendly_title_from_url(url), text=text)
                    )
                    continue

                response = self.session.get(url, timeout=20)
                if response.status_code in {401, 403, 429}:
                    document, links = self._fetch_reader_document(url)
                    if document and self._is_useful_document(document):
                        documents.append(document)
                    self._extend_queue(queue, links, base_host, visited)
                    continue

                response.raise_for_status()
            except requests.RequestException:
                document, links = self._fetch_reader_document(url)
                if document and self._is_useful_document(document):
                    documents.append(document)
                self._extend_queue(queue, links, base_host, visited)
                continue

            if "text/html" not in response.headers.get("content-type", ""):
                continue

            document, links = self._parse_html(url, response.text)
            if document and self._is_useful_document(document):
                documents.append(document)
            self._extend_queue(queue, links, base_host, visited)

        return documents

    def _seed_urls(self) -> list[str]:
        return [self._normalize_url(urljoin(self.base_url, path)) for path in SEED_PATHS if self._normalize_url(urljoin(self.base_url, path))]

    def _parse_html(self, url: str, html: str) -> tuple[SourceDocument | None, list[str]]:
        soup = BeautifulSoup(html, "lxml")
        for element in soup(["script", "style", "noscript", "svg", "form", "header", "footer"]):
            element.decompose()

        title = clean_text(soup.title.get_text(" ")) if soup.title else friendly_title_from_url(url)
        main = soup.find("main") or soup.find("article") or soup.body or soup
        text = self._clean_page_text(main.get_text(" "))
        links = [urljoin(url, link["href"]) for link in soup.find_all("a", href=True)]
        document = SourceDocument(url=url, title=title, text=text) if text else None
        return document, links

    def _fetch_reader_document(self, url: str) -> tuple[SourceDocument | None, list[str]]:
        # SKCT currently blocks plain requests with 403. Jina Reader returns
        # readable Markdown while preserving the original page URL as source.
        reader_url = f"https://r.jina.ai/{url}"
        try:
            response = self.session.get(reader_url, timeout=35)
            response.raise_for_status()
        except requests.RequestException:
            return None, []

        markdown = response.text
        title_match = re.search(r"^Title:\s*(.+)$", markdown, flags=re.MULTILINE)
        source_match = re.search(r"^URL Source:\s*(.+)$", markdown, flags=re.MULTILINE)
        title = clean_text(title_match.group(1)) if title_match else friendly_title_from_url(url)
        source_url = clean_text(source_match.group(1)) if source_match else url

        content = markdown.split("Markdown Content:", 1)[-1]
        text = self._clean_page_text(content)
        links = self._extract_links(markdown, base_url=source_url)
        document = SourceDocument(url=source_url, title=title, text=text) if text else None
        return document, links

    def _extract_links(self, text: str, base_url: str) -> list[str]:
        markdown_links = re.findall(r"\]\((https?://[^)]+)\)", text)
        raw_urls = re.findall(r"https?://[^\s)>\"]+", text)
        links = markdown_links + raw_urls
        return [urljoin(base_url, link.strip()) for link in links]

    def _extend_queue(self, queue: deque[str], links: list[str], base_host: str, visited: set[str]) -> None:
        for link in links:
            next_url = self._normalize_url(link)
            if not next_url:
                continue
            parsed = urlparse(next_url)
            if parsed.netloc != base_host or next_url in visited or next_url in queue:
                continue
            if self._looks_relevant(next_url):
                queue.append(next_url)

    def _clean_page_text(self, text: str) -> str:
        text = re.sub(r"!\[[^\]]*]\([^)]+\)", " ", text)
        text = re.sub(r"\[[^\]]*]\(([^)]+)\)", r" \1 ", text)
        text = re.sub(r"blob:http://localhost/[a-f0-9]+", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"\bBrochure\b", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"Cookie Policy|Privacy Policy|Skip to content", " ", text, flags=re.IGNORECASE)
        return clean_text(text)

    def _is_useful_document(self, document: SourceDocument) -> bool:
        words = document.text.split()
        if len(words) < 60:
            return False
        combined = f"{document.url} {document.title} {document.text[:1200]}".lower()
        return any(keyword in combined for keyword in self.keywords) or document.url.rstrip("/") == self.base_url.rstrip("/")

    def _normalize_url(self, url: str) -> str | None:
        url, _fragment = urldefrag(url)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return None
        return url.rstrip("/")

    def _looks_relevant(self, url: str) -> bool:
        lowered = url.lower()
        if any(skip in lowered for skip in ["wp-login", "mailto:", "tel:", "#", "javascript:"]):
            return False
        return lowered.endswith(".pdf") or any(keyword in lowered for keyword in self.keywords)
