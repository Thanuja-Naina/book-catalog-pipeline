"""Run the full pipeline: scrape -> clean -> load into SQLite -> validate SQL vs Pandas.

Usage:
    python -m src.pipeline                      # all categories (~1,000 books, takes a few minutes)
    python -m src.pipeline --max-categories 3   # quick run
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .clean import clean_books
from .load import load_to_sqlite
from .scrape import scrape_catalog
from .validate import validate

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--max-categories", type=int, default=None, help="only scrape the first N categories")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "books.db")
    args = parser.parse_args()

    print("1/4 Scraping")
    raw = scrape_catalog(args.max_categories)
    raw.to_csv(ROOT / "data" / "books_raw.csv", index=False)

    print("2/4 Cleaning")
    clean = clean_books(raw)
    clean.to_csv(ROOT / "data" / "books_clean.csv", index=False)

    print("3/4 Loading into SQLite")
    load_to_sqlite(clean, args.db)

    print("4/4 Validating SQL against Pandas")
    validate(args.db, expected=clean)
    print("Done.")


if __name__ == "__main__":
    main()

