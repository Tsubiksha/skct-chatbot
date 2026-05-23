import hashlib
import re
import time
from collections import deque
from dataclasses import dataclass
from urllib.parse import urldefrag, urljoin, urlparse

import requests

from backend.app.graph_rag.entity_extractor import detect_page_type
from backend.app.graph_rag.text_cleaner import clean_markdown_reader_text, extract_clean_text

USER_AGENT = "SKCTGraphRAGBot/1.0 Educational Project"
SKIP_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".css", ".js", ".mp4", ".avi", ".mov", ".pdf")
SKIP_PATHS = ("login", "admin", "wp-admin", "wp-login", "cart", "checkout")
SEED_PATHS = [
    "/",
    "/about-us/",
    "/about/",
    "/departments/",
    "/department/",
    "/department/m-e-computer-science-and-engineering/",
    "/department/m-e-computer-science-and-engineering/hods-desk/",
    "/department/computer-science-and-engineering-internet-of-things/",
    "/department/computer-science-and-engineering-internet-of-things/hods-desk-2/",
    "/department/computer-science-and-engineering-artificial-intelligence-and-machine-learning/",
    "/department/computer-science-and-engineering-artificial-intelligence-and-machine-learning/hods-desk-2/",
    "/department/computer-science-and-engineering-cyber-security/",
    "/department/computer-science-and-engineering-cyber-security/hods-desk/",
    "/department/b-tech-artificial-intelligence-and-data-science/",
    "/department/b-tech-artificial-intelligence-and-data-science/hods-desk/",
    "/department/electronics-and-communication-engineering/",
    "/department/electrical-and-electronics-engineering/",
    "/department/information-technology/",
    "/department/mechanical-engineering/",
    "/department/civil-engineering/",
    "/placement/",
    "/placements/",
    "/academics/",
    "/admission/",
    "/admissions/",
    "/research/",
    "/events/",
    "/facilities/",
    "/infrastructure/",
    "/library/",
    "/hostel/",
    "/transport/",
    "/contact/",
    "/regulations/",
]


@dataclass
class ScrapedPage:
    url: str
    title: str
    page_type: str
    content: str
    content_hash: str


@dataclass
class ScrapeResult:
    pages: list[ScrapedPage]
    pages_visited: int
    errors: list[str]


class SKCTWebsiteScraper:
    def __init__(self, base_url: str = "https://skct.edu.in/", delay_seconds: float = 1.0):
        self.base_url = base_url
        self.base_host = urlparse(base_url).netloc.replace("www.", "")
        self.delay_seconds = delay_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def scrape(self, max_pages: int = 30, max_depth: int = 2) -> ScrapeResult:
        queue: deque[tuple[str, int]] = deque((url, 0) for url in self._seed_urls())
        visited: set[str] = set()
        pages: list[ScrapedPage] = []
        errors: list[str] = []

        while queue and len(visited) < max_pages:
            url, depth = queue.popleft()
            normalized = self._normalize_url(url)
            if not normalized or normalized in visited or self._should_skip(normalized):
                continue

            visited.add(normalized)
            time.sleep(self.delay_seconds)

            try:
                page, links = self._fetch_page(normalized)
            except requests.RequestException as exc:
                errors.append(f"{normalized}: {exc}")
                continue

            if page and len(page.content.split()) >= 40:
                pages.append(page)

            if depth < max_depth:
                for link in links:
                    next_url = self._normalize_url(urljoin(normalized, link))
                    if next_url and next_url not in visited and not self._should_skip(next_url):
                        queue.append((next_url, depth + 1))

        return ScrapeResult(pages=pages, pages_visited=len(visited), errors=errors)

    def _fetch_page(self, url: str) -> tuple[ScrapedPage | None, list[str]]:
        response = self.session.get(url, timeout=25)
        if response.status_code in {401, 403, 429}:
            return self._fetch_reader_page(url)
        response.raise_for_status()

        if "text/html" not in response.headers.get("content-type", ""):
            return None, []

        title, content = extract_clean_text(response.text)
        links = re.findall(r'href=["\']([^"\']+)["\']', response.text, flags=re.IGNORECASE)
        return self._make_page(url, title, content), links

    def _fetch_reader_page(self, url: str) -> tuple[ScrapedPage | None, list[str]]:
        # SKCT may block plain requests. This text fallback preserves the
        # original website as source while returning readable Markdown.
        reader_url = f"https://r.jina.ai/{url}"
        response = self.session.get(reader_url, timeout=35)
        response.raise_for_status()
        title, content = clean_markdown_reader_text(response.text)
        links = re.findall(r"https?://[^\s)>\"]+", response.text)
        return self._make_page(url, title, content), links

    def _make_page(self, url: str, title: str, content: str) -> ScrapedPage:
        content_hash = hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()
        page_type = detect_page_type(url, title, content)
        return ScrapedPage(url=url, title=title, page_type=page_type, content=content, content_hash=content_hash)

    def _seed_urls(self) -> list[str]:
        seeds = [urljoin(self.base_url, path) for path in SEED_PATHS]
        seeds.extend(self._sitemap_urls())
        return list(dict.fromkeys(seeds))

    def _sitemap_urls(self) -> list[str]:
        sitemap_urls = [urljoin(self.base_url, "sitemap.xml"), urljoin(self.base_url, "sitemap_index.xml")]
        discovered: list[str] = []
        for sitemap_url in sitemap_urls:
            try:
                response = self.session.get(sitemap_url, timeout=20)
                if response.status_code >= 400:
                    continue
                discovered.extend(re.findall(r"<loc>\s*([^<]+)\s*</loc>", response.text, flags=re.IGNORECASE))
            except requests.RequestException:
                continue
        return [url for url in discovered if self._normalize_url(url)]

    def _normalize_url(self, url: str) -> str | None:
        url, _fragment = urldefrag(url)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return None
        host = parsed.netloc.replace("www.", "")
        if host != self.base_host:
            return None
        return url.rstrip("/")

    def _should_skip(self, url: str) -> bool:
        lowered = url.lower()
        return lowered.endswith(SKIP_EXTENSIONS) or any(path in lowered for path in SKIP_PATHS)
