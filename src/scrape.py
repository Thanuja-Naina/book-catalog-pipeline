"""Scrape the book catalog at https://books.toscrape.com (a sandbox site built for scraping practice).

Fetching and parsing are separate functions so the parsers can be tested on saved HTML.
"""
from __future__ import annotations

import time
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://books.toscrape.com/"
HEADERS = {"User-Agent": "book-catalog-pipeline/1.0 (learning project)"}
REQUEST_DELAY_SECONDS = 0.5


def fetch(url: str, session: requests.Session | None = None, retries: int = 3) -> str:
    """GET a page with simple retries. The site serves UTF-8 but does not always say so."""
    session = session or requests.Session()
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()
            response.encoding = "utf-8"
            return response.text
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(2 * attempt)
    raise RuntimeError("unreachable")


def parse_categories(html: str, base_url: str = BASE_URL) -> list[tuple[str, str]]:
    """Return [(category_name, category_url)] from the sidebar, skipping the 'Books' root entry."""
    soup = BeautifulSoup(html, "html.parser")
    links = soup.select("div.side_categories ul li ul li a")
    return [(a.get_text(strip=True), urljoin(base_url, a["href"])) for a in links]


def parse_listing(html: str, category: str, page_url: str) -> tuple[list[dict], str | None]:
    """Parse one category listing page. Returns (books, next_page_url or None)."""
    soup = BeautifulSoup(html, "html.parser")
    books = []
    for pod in soup.select("article.product_pod"):
        link = pod.select_one("h3 a")
        rating_tag = pod.select_one("p.star-rating")
        rating_classes = [c for c in (rating_tag.get("class", []) if rating_tag else []) if c != "star-rating"]
        books.append(
            {
                "title": link["title"],
                "category": category,
                "price_raw": pod.select_one("p.price_color").get_text(strip=True),
                "rating_raw": rating_classes[0] if rating_classes else None,
                "availability_raw": pod.select_one("p.availability").get_text(strip=True),
                "url": urljoin(page_url, link["href"]),
            }
        )
    next_link = soup.select_one("li.next a")
    return books, (urljoin(page_url, next_link["href"]) if next_link else None)


def scrape_catalog(max_categories: int | None = None, session: requests.Session | None = None) -> pd.DataFrame:
    """Scrape every category (or the first `max_categories`) into one raw DataFrame."""
    session = session or requests.Session()
    categories = parse_categories(fetch(BASE_URL, session))
    if max_categories:
        categories = categories[:max_categories]

    rows: list[dict] = []
    for name, url in categories:
        page_url: str | None = url
        while page_url:
            books, page_url_next = parse_listing(fetch(page_url, session), name, page_url)
            rows.extend(books)
            page_url = page_url_next
            time.sleep(REQUEST_DELAY_SECONDS)
        print(f"  scraped category {name!r}: {sum(1 for r in rows if r['category'] == name)} books")
    return pd.DataFrame(rows)
