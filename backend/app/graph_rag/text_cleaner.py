import re
from bs4 import BeautifulSoup


NOISE_PATTERNS = [
    r"skip to content",
    r"cookie policy",
    r"privacy policy",
    r"all rights reserved",
    r"follow us",
]


def clean_text(text: str) -> str:
    lines = []
    seen = set()
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        lowered = line.lower()
        if any(re.search(pattern, lowered) for pattern in NOISE_PATTERNS):
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        lines.append(line)

    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def extract_clean_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript", "svg", "iframe", "form", "nav", "footer"]):
        tag.decompose()

    for selector in [".cookie", ".cookies", ".ad", ".ads", ".popup", ".modal", "#cookie", "#cookies"]:
        for node in soup.select(selector):
            node.decompose()

    title = soup.title.get_text(" ", strip=True) if soup.title else "Untitled"
    content_nodes = soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th"])
    text = "\n".join(node.get_text(" ", strip=True) for node in content_nodes)
    if len(text.split()) < 40:
        text = soup.get_text("\n", strip=True)

    return title.strip() or "Untitled", clean_text(text)


def clean_markdown_reader_text(markdown: str) -> tuple[str, str]:
    title_match = re.search(r"^Title:\s*(.+)$", markdown, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "Untitled"
    content = markdown.split("Markdown Content:", 1)[-1]
    content = re.sub(r"!\[[^\]]*]\([^)]+\)", " ", content)
    content = re.sub(r"\[[^\]]+]\(([^)]+)\)", r"\1", content)
    content = re.sub(r"#{1,6}\s*", "", content)
    return title, clean_text(content)
