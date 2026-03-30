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
}

REQUIRED_COLUMNS = ("title", "year", "genres", "keywords", "overview")
OPTIONAL_COLUMNS = ("director", "cast")
TEXT_COLUMNS = ("title", "genres", "keywords", "director", "cast", "overview")


def _normalize_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    renamed = dataframe.rename(columns={col: COLUMN_ALIASES.get(col, col) for col in dataframe.columns})
    return renamed


def _clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return " ".join(str(value).replace("|", ", ").split())


def load_movies(csv_path: Path) -> pd.DataFrame:
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
    dataframe = dataframe.drop_duplicates(subset=["title", "year"]).reset_index(drop=True)

    dataframe["feature_text"] = dataframe.apply(
        lambda row: " ".join(
            part
            for part in (
                row["title"],
                row["genres"],
                row["keywords"],
                row["director"],
                row["cast"],
                row["overview"],
            )
            if part
        ),
        axis=1,
    )
    return dataframe
