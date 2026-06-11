import json
import re
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright
from sentence_transformers import SentenceTransformer


model = SentenceTransformer("all-MiniLM-L6-v2")
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # Go up from src/ to root
DATA_DIR = PROJECT_ROOT / "data"


BAD_WORDS = [
    "login",
    "menu",
    "subscribe",
    "cookie",
    "privacy",
    "terms",
    "©",
    "all rights reserved",
]


def fetch_text(url):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")

        # Remove obvious layout/interaction elements before text extraction.
        page.evaluate(
            """
            () => {
                const elements = document.querySelectorAll('nav, footer, header, button, svg');
                elements.forEach(el => el.remove());
            }
            """
        )

        text = page.inner_text("body")
        browser.close()

    return text


def clean_text(text):
    lines = text.split("\n")
    clean_lines = []

    for line in lines:
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) < 40:
            continue
        if any(b in line.lower() for b in BAD_WORDS):
            continue
        clean_lines.append(line)

    return "\n".join(clean_lines)


def chunk_text(text, max_sentences=4):
    sentences = [s.strip() for s in re.split(r"(?<=[.!?]) +", text) if s.strip()]
    chunks = []
    current = []

    for sentence in sentences:
        current.append(sentence)
        if len(current) >= max_sentences:
            chunk = " ".join(current).strip()
            chunks.append(chunk)
            current = []

    if current:
        chunks.append(" ".join(current).strip())

    return chunks


def is_good_chunk(chunk):
    return len(chunk) > 100 and chunk.count(" ") > 15


def main():
    with open(DATA_DIR / "urls.txt", encoding="utf-8") as f:
        urls = [u.strip() for u in f.readlines() if u.strip()]

    # Preserve URL order while avoiding duplicate fetches.
    unique_urls = list(dict.fromkeys(urls))

    all_chunks = []

    for url in unique_urls:
        print("Scraping:", url)
        text = fetch_text(url)
        text = clean_text(text)

        page_chunks = [c for c in chunk_text(text, max_sentences=4) if is_good_chunk(c)]

        for chunk in page_chunks:
            all_chunks.append({"url": url, "text": chunk})

    print("Total chunks:", len(all_chunks))
    if len(all_chunks) > 10:
        print("\nSAMPLE CHUNK:\n")
        print(all_chunks[10]["text"])

    with open(DATA_DIR / "data.json", "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False)

    texts = [c["text"] for c in all_chunks]
    embeddings = model.encode(texts, normalize_embeddings=True)
    np.save(str(DATA_DIR / "embeddings.npy"), embeddings)

    print("Done!")


if __name__ == "__main__":
    main()
