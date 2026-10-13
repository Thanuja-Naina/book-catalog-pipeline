# Book Catalog Data Pipeline

An end-to-end data pipeline that **scrapes** a book catalog, **cleans** it with Pandas, **loads** it into a **normalized SQLite** database, and **validates** that SQL query results match equivalent Pandas operations.

The source is [books.toscrape.com](https://books.toscrape.com), a sandbox site built for practising web scraping (about 1,000 books across 50 categories).

**Tech:** Python, requests, BeautifulSoup, pandas, SQLite, pytest

## Pipeline

```
scrape.py ──► clean.py ──► load.py ──► validate.py
 requests +    types,        normalized   5 checks: SQL result
 BeautifulSoup duplicates,   SQLite       vs Pandas result
 (pagination,  missing        (FKs,
 retries)      values)        constraints)
```

1. **Scrape** (`src/scrape.py`): reads the category list from the sidebar, follows pagination in each category, and extracts title, price, star rating, availability and URL. Requests are retried on failure and spaced 0.5 s apart to be polite to the server. Fetching and parsing are separate functions, so the parsers can be tested on saved HTML.
2. **Clean** (`src/clean.py`): converts prices like `£51.77` to floats (also handles the `Â£` encoding glitch), maps rating words (`Three`) to integers, turns availability text into a boolean, collapses stray whitespace in titles, and drops duplicate URLs and rows with missing or invalid values.
3. **Load** (`src/load.py`): writes to SQLite in third normal form. Categories live in their own table and `books` references them through a foreign key, with `CHECK` constraints (price > 0, rating 1 to 5), a `UNIQUE` URL and indexes on category and rating.
4. **Validate** (`src/validate.py`): runs five analytical queries in SQL and the same logic in Pandas on the cleaned data, then fails if they disagree. Because the Pandas side comes from the cleaned DataFrame rather than the database, it also catches rows lost or corrupted during loading.

Checks: books per category, average price per category, rating distribution, in-stock share, and 5-star books priced over 40.

## Database schema

```sql
categories(category_id PK, name UNIQUE)
books(book_id PK, title, category_id FK -> categories, price, rating, in_stock, url UNIQUE)
```

## Run it

```bash
pip install -r requirements.txt
python -m src.pipeline --max-categories 3   # quick run (a few categories)
python -m src.pipeline                      # full catalog, a few minutes
```

Outputs are written to `data/`: `books_raw.csv`, `books_clean.csv` and `books.db`. Explore the database with any SQLite client, for example:

```sql
SELECT c.name, COUNT(*) AS books, ROUND(AVG(b.price), 2) AS avg_price
FROM books b JOIN categories c ON c.category_id = b.category_id
GROUP BY c.name ORDER BY avg_price DESC LIMIT 10;
```

## Tests

```bash
pytest
```

The 9 tests run offline against generated HTML that uses the same markup as the site. They cover category and listing parsing, pagination, price and rating cleaning (including duplicates and mis-encoded prices), the database schema and constraints, a passing validation run, and a failing validation run when a row is deleted from the database.

## Notes

- The scraper depends on the site's HTML structure. If the markup changes, update the selectors in `parse_categories` and `parse_listing`.
- Scrape politely: keep the request delay and only run the full scrape when you need it.

## Possible next steps

- Scrape each book's detail page for UPC, description and stock count.
- Schedule the pipeline and load incrementally instead of rebuilding the database.
- Add price-history tracking with a snapshot table.
