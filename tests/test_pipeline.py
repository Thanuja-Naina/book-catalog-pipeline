"""Tests run fully offline: pages are generated HTML in the same markup as books.toscrape.com."""
import sqlite3

import pandas as pd
import pytest

from src import scrape
from src.clean import clean_books, parse_price
from src.load import load_to_sqlite
from src.validate import validate

BASE = "https://books.toscrape.com/"


def pod(slug: str, title: str, price: str, rating: str, availability: str = "In stock") -> str:
    return f"""
    <li class="col-xs-6"><article class="product_pod">
      <div class="image_container"><a href="{slug}/index.html"><img alt="{title}"></a></div>
      <p class="star-rating {rating}"><i class="icon-star"></i></p>
      <h3><a href="{slug}/index.html" title="{title}">{title[:20]}...</a></h3>
      <div class="product_price">
        <p class="price_color">{price}</p>
        <p class="instock availability"><i class="icon-ok"></i>
            {availability}
        </p>
      </div>
    </article></li>"""


def page(pods: list[str], next_href: str | None = None) -> str:
    nxt = f'<li class="next"><a href="{next_href}">next</a></li>' if next_href else ""
    return f"<html><body><ol>{''.join(pods)}</ol><ul class='pager'>{nxt}</ul></body></html>"


HOME = """<html><body><div class="side_categories"><ul class="nav"><li>
  <a href="catalogue/category/books_1/index.html">Books</a>
  <ul>
    <li><a href="catalogue/category/books/travel_2/index.html">  Travel </a></li>
    <li><a href="catalogue/category/books/mystery_3/index.html">Mystery</a></li>
  </ul></li></ul></div></body></html>"""

PAGES = {
    BASE: HOME,
    BASE + "catalogue/category/books/travel_2/index.html": page(
        [
            pod("its-only-the-himalayas_1", "It's Only the Himalayas", "Â£45.17", "Two"),
            pod("full-moon_2", "Full Moon  over   Noahs Ark", "£49.43", "Four"),
        ],
        next_href="page-2.html",
    ),
    BASE + "catalogue/category/books/travel_2/page-2.html": page(
        [
            pod("see-america_3", "See America", "£48.87", "Three"),
            pod("its-only-the-himalayas_1", "It's Only the Himalayas", "£45.17", "Two"),  # duplicate listing
        ]
    ),
    BASE + "catalogue/category/books/mystery_3/index.html": page(
        [
            pod("sharp-objects_4", "Sharp Objects", "£47.82", "Four"),
            pod("in-a-dark-dark-wood_5", "In a Dark, Dark Wood", "£19.63", "One"),
            pod("the-past-never-ends_6", "The Past Never Ends", "£56.50", "Four", availability="Out of stock"),
            pod("the-murder-of-roger_7", "The Murder of Roger Ackroyd", "£44.10", "Five"),
        ]
    ),
}


@pytest.fixture()
def offline(monkeypatch):
    def fake_fetch(url, session=None, retries=3):
        return PAGES[url]

    monkeypatch.setattr(scrape, "fetch", fake_fetch)
    monkeypatch.setattr(scrape, "REQUEST_DELAY_SECONDS", 0)


def test_parse_categories_skips_root_and_strips_names():
    cats = scrape.parse_categories(HOME)
    assert [name for name, _ in cats] == ["Travel", "Mystery"]
    assert cats[0][1] == BASE + "catalogue/category/books/travel_2/index.html"


def test_parse_listing_extracts_fields_and_next_link():
    url = BASE + "catalogue/category/books/travel_2/index.html"
    books, nxt = scrape.parse_listing(PAGES[url], "Travel", url)
    assert len(books) == 2
    assert books[0]["title"] == "It's Only the Himalayas"
    assert books[0]["rating_raw"] == "Two"
    assert nxt == BASE + "catalogue/category/books/travel_2/page-2.html"


def test_scrape_follows_pagination(offline):
    raw = scrape.scrape_catalog()
    assert len(raw) == 8  # 4 on travel (incl. duplicate) + 4 on mystery
    assert set(raw["category"]) == {"Travel", "Mystery"}


def test_parse_price_handles_mojibake():
    assert parse_price("£51.77") == 51.77
    assert parse_price("Â£51.77") == 51.77
    assert parse_price("free") is None


def test_clean_removes_duplicates_and_normalises_types(offline):
    clean = clean_books(scrape.scrape_catalog())
    assert len(clean) == 7
    assert clean["url"].is_unique
    assert clean["price"].dtype == float
    assert clean["rating"].between(1, 5).all()
    assert "Full Moon over Noahs Ark" in set(clean["title"])  # whitespace collapsed
    assert not clean.loc[clean["title"] == "The Past Never Ends", "in_stock"].item()


def test_full_pipeline_loads_normalized_schema_and_validates(offline, tmp_path):
    clean = clean_books(scrape.scrape_catalog())
    db = tmp_path / "books.db"
    load_to_sqlite(clean, db)

    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 7
        assert conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 2
        # categories stored once, books reference them
        names = [r[0] for r in conn.execute("SELECT name FROM categories ORDER BY name")]
        assert names == ["Mystery", "Travel"]
        fk = conn.execute("PRAGMA foreign_key_list(books)").fetchall()
        assert fk and fk[0][2] == "categories"

    results = validate(db, expected=clean)
    assert all(results.values()) and len(results) == 5


def test_validation_fails_when_database_differs_from_cleaned_data(offline, tmp_path):
    clean = clean_books(scrape.scrape_catalog())
    db = tmp_path / "books.db"
    load_to_sqlite(clean, db)

    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM books WHERE book_id = 1")  # simulate a lost row during load
        conn.commit()

    with pytest.raises(AssertionError, match="disagree"):
        validate(db, expected=clean)


def test_database_constraints_reject_invalid_values(offline, tmp_path):
    clean = clean_books(scrape.scrape_catalog())
    db = tmp_path / "books.db"
    load_to_sqlite(clean, db)

    with sqlite3.connect(db) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE books SET rating = 9 WHERE book_id = 1")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE books SET price = -5 WHERE book_id = 1")


def test_clean_drops_rows_with_missing_required_fields():
    raw = pd.DataFrame(
        [
            {"title": "Good", "category": "A", "price_raw": "£10.00", "rating_raw": "Three", "availability_raw": "In stock", "url": "u1"},
            {"title": "No rating", "category": "A", "price_raw": "£10.00", "rating_raw": None, "availability_raw": "In stock", "url": "u2"},
            {"title": "No price", "category": "A", "price_raw": "n/a", "rating_raw": "Two", "availability_raw": "In stock", "url": "u3"},
        ]
    )
    clean = clean_books(raw)
    assert list(clean["title"]) == ["Good"]
