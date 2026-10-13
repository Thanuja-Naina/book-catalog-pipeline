"""Load the cleaned books into a normalized SQLite database.

Schema (3NF): categories are stored once and referenced from books by a foreign key.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

SCHEMA = """
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS books;
DROP TABLE IF EXISTS categories;

CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE
);

CREATE TABLE books (
    book_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(category_id),
    price       REAL    NOT NULL CHECK (price > 0),
    rating      INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    in_stock    INTEGER NOT NULL CHECK (in_stock IN (0, 1)),
    url         TEXT    NOT NULL UNIQUE
);

CREATE INDEX idx_books_category ON books(category_id);
CREATE INDEX idx_books_rating   ON books(rating);
"""


def load_to_sqlite(df: pd.DataFrame, db_path: str | Path) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO categories(name) VALUES (?)",
            [(c,) for c in sorted(df["category"].unique())],
        )
        category_ids = dict(conn.execute("SELECT name, category_id FROM categories"))
        conn.executemany(
            "INSERT INTO books(title, category_id, price, rating, in_stock, url) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (r.title, category_ids[r.category], float(r.price), int(r.rating), int(r.in_stock), r.url)
                for r in df.itertuples(index=False)
            ],
        )
    print(f"Loaded {len(df)} books and {df['category'].nunique()} categories into {db_path}")
