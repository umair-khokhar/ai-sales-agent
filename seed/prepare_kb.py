"""
Crawls hubbase.io and indexes all pages into HydraDB under tenant 'hubbase'.
Uses the official HydraDB Python SDK (upload.add_memory).
"""

import json
import os
import re
import time
from collections import deque
from urllib.parse import urljoin, urlparse

from dotenv import load_dotenv
load_dotenv()

import requests
from bs4 import BeautifulSoup
from hydra_db import HydraDB
from hydra_db.types import MemoryItem

# ── Config (all overridable via .env or environment variables) ────────────────
API_KEY   = os.environ["HYDRADB_API_KEY"]
TENANT_ID = os.environ.get("SEED_TENANT_ID", "hubbase")
START_URL = os.environ.get("SEED_START_URL", "https://www.hubbase.io")
DELAY     = float(os.environ.get("SEED_DELAY", "0.8"))   # seconds between fetches
MAX_PAGES = int(os.environ.get("SEED_MAX_PAGES", "0"))    # 0 = unlimited

CRAWL_HEADERS = {
    "User-Agent": "HydraDB-Indexer/1.0 (+https://hydradb.com)",
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def is_same_domain(url: str, domain: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc == domain or parsed.netloc.endswith(f".{domain}")


def extract_title_and_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "noscript", "svg", "iframe"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    main  = soup.find("main") or soup.find("article") or soup.body
    raw   = main.get_text(separator="\n") if main else soup.get_text(separator="\n")
    lines = [l.strip() for l in raw.splitlines()]
    body  = "\n".join(l for l in lines if l)
    return title, body


def collect_links(html: str, page_url: str, domain: str) -> list[str]:
    soup  = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full = urljoin(page_url, href).split("#")[0].rstrip("/")
        if full and is_same_domain(full, domain):
            links.add(full)
    return list(links)


def slug(url: str, max_len: int = 80) -> str:
    return re.sub(r"[^a-z0-9]", "_", url.lower())[:max_len]


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    domain = urlparse(START_URL).netloc   # www.hubbase.io

    print("=" * 60)
    print(f"Indexing  {START_URL}")
    print(f"Tenant    {TENANT_ID}")
    print(f"Delay     {DELAY}s   Max pages: {MAX_PAGES or 'unlimited'}")
    print("=" * 60)

    client = HydraDB(token=API_KEY)

    # Ensure tenant exists (ignore plan-limit 403 — tenant may already be set up)
    try:
        client.tenant.create(tenant_id=TENANT_ID)
        print(f"[hydra] Tenant '{TENANT_ID}' created.")
    except Exception as e:
        print(f"[hydra] Tenant note: {str(e)[:120]}")

    visited = set()
    queue   = deque([START_URL.rstrip("/")])
    indexed = 0
    failed  = 0

    while queue:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        print(f"\n[crawl] {url}")
        try:
            resp = requests.get(url, headers=CRAWL_HEADERS, timeout=15,
                                allow_redirects=True)
        except Exception as e:
            print(f"  [error] {e}")
            failed += 1
            continue

        if resp.status_code != 200:
            print(f"  [skip] HTTP {resp.status_code}")
            continue
        if "text/html" not in resp.headers.get("content-type", ""):
            print("  [skip] not HTML")
            continue

        html         = resp.text
        title, body  = extract_title_and_text(html)
        full_text    = f"# {title}\n\n{body}" if title else body

        if len(full_text.strip()) < 50:
            print("  [skip] too short")
            continue

        print(f"  [index] {len(full_text):,} chars … ", end="", flush=True)

        item = MemoryItem(
            source_id=slug(url),
            title=title or url,
            text=full_text,
            is_markdown=False,
            infer=False,
            document_metadata=json.dumps({"source_url": url, "site": "hubbase.io"}),
        )

        try:
            client.upload.add_memory(
                memories=[item],
                tenant_id=TENANT_ID,
                upsert=True,
            )
            print("OK")
            indexed += 1
        except Exception as e:
            print(f"FAILED — {e}")
            failed += 1

        # Stop if page cap reached
        if MAX_PAGES and indexed >= MAX_PAGES:
            print(f"\n[crawl] Reached SEED_MAX_PAGES={MAX_PAGES}, stopping.")
            break

        # Enqueue new links
        for link in collect_links(html, url, domain):
            if link not in visited:
                queue.append(link)

        time.sleep(DELAY)

    print("\n" + "=" * 60)
    print(f"Done.  Indexed: {indexed}  Failed: {failed}  Visited: {len(visited)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
