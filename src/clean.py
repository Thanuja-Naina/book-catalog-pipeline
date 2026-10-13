"""Clean the raw scraped data: types, duplicates, missing values."""
from __future__ import annotations

import re

import pandas as pd

RATING_MAP = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
REQUIRED = ["title", "category", "price", "rating", "url"]


def parse_price(raw: str) -> float | None:
    """'£51.77' (or mis-decoded 'Â£51.77') -> 51.77"""
    match = re.search(r"(\d+(?:\.\d+)?)", str(raw))
    return float(match.group(1)) if match else None


def clean_books(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()

    df["title"] = df["title"].astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
    df["category"] = df["category"].astype("string").str.strip()
    df["price"] = df["price_raw"].map(parse_price)
    df["rating"] = df["rating_raw"].map(RATING_MAP)
    df["in_stock"] = df["availability_raw"].astype("string").str.contains("in stock", case=False, na=False)

    before = len(df)
    df = df.dropna(subset=REQUIRED)
    df = df[df["price"] > 0]
    df = df.drop_duplicates(subset="url", keep="first")
    df["rating"] = df["rating"].astype(int)
    df = df[["title", "category", "price", "rating", "in_stock", "url"]].reset_index(drop=True)

    print(f"Cleaned {before} raw rows -> {len(df)} rows ({before - len(df)} dropped as invalid or duplicate)")
    return df
