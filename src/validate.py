"""Validate SQL queries against equivalent Pandas operations on the same data.

Each check computes the same answer twice, once in SQLite and once in Pandas,
and fails loudly if they disagree. This catches bad joins, wrong filters and load errors.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pandas as pd

JOINED = """
SELECT b.title, c.name AS category, b.price, b.rating, b.in_stock
FROM books b JOIN categories c ON c.category_id = b.category_id
"""

CHECKS: dict[str, tuple[str, Callable[[pd.DataFrame], pd.DataFrame]]] = {
    "books per category": (
        """SELECT c.name AS category, COUNT(*) AS n
           FROM books b JOIN categories c ON c.category_id = b.category_id
           GROUP BY c.name ORDER BY c.name""",
        lambda df: df.groupby("category").size().rename("n").reset_index().sort_values("category"),
    ),
    "average price per category": (
        """SELECT c.name AS category, ROUND(AVG(b.price), 2) AS avg_price
           FROM books b JOIN categories c ON c.category_id = b.category_id
           GROUP BY c.name ORDER BY c.name""",
        lambda df: df.groupby("category")["price"].mean().round(2).rename("avg_price").reset_index().sort_values("category"),
    ),
    "rating distribution": (
        "SELECT rating, COUNT(*) AS n FROM books GROUP BY rating ORDER BY rating",
        lambda df: df.groupby("rating").size().rename("n").reset_index().sort_values("rating"),
    ),
    "in-stock share": (
        "SELECT ROUND(AVG(in_stock), 4) AS share FROM books",
        lambda df: pd.DataFrame({"share": [round(df["in_stock"].mean(), 4)]}),
    ),
    "5-star books over 40 GBP": (
        "SELECT COUNT(*) AS n FROM books WHERE rating = 5 AND price > 40",
        lambda df: pd.DataFrame({"n": [int(((df["rating"] == 5) & (df["price"] > 40)).sum())]}),
    ),
}


def validate(db_path: str | Path, expected: pd.DataFrame | None = None) -> dict[str, bool]:
    """Compare SQL answers from the database with Pandas answers.

    Pass the cleaned DataFrame that was loaded as `expected` so the Pandas side is independent of the
    database. That makes the check catch load errors (missing rows, wrong joins), not just query bugs.
    """
    with sqlite3.connect(db_path) as conn:
        df = expected if expected is not None else pd.read_sql_query(JOINED, conn)
        results = {}
        for name, (sql, pandas_fn) in CHECKS.items():
            sql_result = pd.read_sql_query(sql, conn).reset_index(drop=True)
            pandas_result = pandas_fn(df).reset_index(drop=True)
            try:
                pd.testing.assert_frame_equal(
                    sql_result, pandas_result, check_dtype=False, check_exact=False, atol=1e-4
                )
                ok = True
            except AssertionError:
                ok = False
            results[name] = ok
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if not all(results.values()):
        raise AssertionError(f"SQL and Pandas results disagree: {[k for k, v in results.items() if not v]}")
    return results
