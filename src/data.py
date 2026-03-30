from __future__ import annotations

from pathlib import Path

import pandas as pd


COLUMN_ALIASES = {
    "movie_title": "title",
    "name": "title",
    "release_year": "year",
    "genre": "genres",
    "plot": "overview",
    "description": "overview",
    "summary": "overview",
    "series_title": "title",
    "show_title": "title",
}

REQUIRED_COLUMNS = (
    "title",
    "year",
    "country",
    "language",
    "status",
    "genres",
    "themes",
    "keywords",
    "network",
    "cast",
    "aliases",
    "overview",
)
OPTIONAL_COLUMNS = ("watch_hint", "poster_url")
TEXT_COLUMNS = (
    "title",
    "country",
    "language",
    "status",
    "genres",
    "themes",
    "keywords",
    "network",
    "cast",
    "aliases",
    "overview",
    "watch_hint",
    "poster_url",
)


def _normalize_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    return dataframe.rename(columns={col: COLUMN_ALIASES.get(col, col) for col in dataframe.columns})


def _clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return " ".join(str(value).replace("|", ", ").split())


def load_catalog(csv_path: Path) -> pd.DataFrame:
    dataframe = pd.read_csv(csv_path)
    dataframe = _normalize_columns(dataframe)

    missing = [column for column in REQUIRED_COLUMNS if column not in dataframe.columns]
    if missing:
        missing_text = ", ".join(missing)
        raise ValueError(f"Dataset is missing required columns: {missing_text}")

    for column in OPTIONAL_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = ""

    for column in TEXT_COLUMNS:
        dataframe[column] = dataframe[column].map(_clean_text)

    dataframe["year"] = pd.to_numeric(dataframe["year"], errors="coerce").fillna(0).astype(int)
    dataframe = dataframe.drop_duplicates(subset=["title", "year", "country"]).reset_index(drop=True)

    dataframe["feature_text"] = dataframe.apply(
        lambda row: " ".join(
            part
            for part in (
                row["title"],
                row["aliases"],
                row["country"],
                row["language"],
                row["status"],
                row["genres"],
                row["themes"],
                row["keywords"],
                row["network"],
                row["cast"],
                row["overview"],
            )
            if part
        ),
        axis=1,
    )
    return dataframe


def load_movies(csv_path: Path) -> pd.DataFrame:
    return load_catalog(csv_path)
