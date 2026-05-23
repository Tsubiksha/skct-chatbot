from io import BytesIO

import requests
from pypdf import PdfReader

from backend.utils.text import clean_text


def extract_pdf_text(url: str, timeout: int = 20) -> str:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()

    reader = PdfReader(BytesIO(response.content))
    pages = [page.extract_text() or "" for page in reader.pages]
    return clean_text(" ".join(pages))
