from __future__ import annotations

from pathlib import Path

import pandas as pd


COLUMN_ALIASES = {
    "movie_title": "title",
    "name": "title",
    "series_title": "title",
    "show_title": "title",
    "release_year": "year",
    "genre": "genres",
    "plot": "overview",
    "description": "overview",
    "summary": "overview",
    "short_summary": "overview",
    "main_themes": "themes",
}

FINAL_COLUMNS = (
    "content_type",
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
    "watch_hint",
    "poster_url",
)

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
    return dataframe.rename(columns={column: COLUMN_ALIASES.get(column, column) for column in dataframe.columns})


def _clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return " ".join(str(value).replace("|", ", ").split())


def _clean_series(series: pd.Series | None) -> pd.Series | None:
    if series is None:
        return None
    return series.map(_clean_text)


def _first_non_empty(dataframe: pd.DataFrame, *columns: str) -> pd.Series:
    result = pd.Series([""] * len(dataframe), index=dataframe.index, dtype="object")
    for column in columns:
        if column not in dataframe.columns:
            continue
        candidate = _clean_series(dataframe[column]).fillna("")
        result = result.where(result != "", candidate)
    return result.fillna("")


def _derive_years(dataframe: pd.DataFrame) -> pd.Series:
    if "year" in dataframe.columns:
        years = pd.to_numeric(dataframe["year"], errors="coerce")
    else:
        years = pd.Series([pd.NA] * len(dataframe), index=dataframe.index, dtype="Float64")

    if "first_air_date" in dataframe.columns:
        derived = pd.to_datetime(dataframe["first_air_date"], errors="coerce").dt.year
        years = years.fillna(derived)

    return years.fillna(0).astype(int)


def _build_aliases(dataframe: pd.DataFrame) -> pd.Series:
    explicit_aliases = _first_non_empty(dataframe, "aliases")
    original_titles = _first_non_empty(dataframe, "original_title", "original_name")
    titles = _first_non_empty(dataframe, "title")

    aliases: list[str] = []
    combined = []
    for title, original_title, alias_text in zip(titles, original_titles, explicit_aliases):
        aliases.clear()
        for candidate in (alias_text, original_title):
            cleaned = _clean_text(candidate)
            if cleaned and cleaned.lower() != title.lower() and cleaned.lower() not in {item.lower() for item in aliases}:
                aliases.append(cleaned)
        combined.append(", ".join(aliases))

    return pd.Series(combined, index=dataframe.index, dtype="object")


def _build_keywords(dataframe: pd.DataFrame) -> pd.Series:
    explicit_keywords = _first_non_empty(dataframe, "keywords")
    themes = _first_non_empty(dataframe, "themes")
    genres = _first_non_empty(dataframe, "genres")
    networks = _first_non_empty(dataframe, "network")

    keywords: list[str] = []
    combined = []
    for explicit, theme_text, genre_text, network in zip(explicit_keywords, themes, genres, networks):
        keywords.clear()
        for chunk in (explicit, theme_text, genre_text, network):
            for item in [part.strip() for part in str(chunk).split(",") if part and part.strip()]:
                if item.lower() not in {value.lower() for value in keywords}:
                    keywords.append(item)
        combined.append(", ".join(keywords))

    return pd.Series(combined, index=dataframe.index, dtype="object")


def _build_watch_hints(dataframe: pd.DataFrame) -> pd.Series:
    explicit_hints = _first_non_empty(dataframe, "watch_hint")
    networks = _first_non_empty(dataframe, "network")
    statuses = _first_non_empty(dataframe, "status")

    hints = []
    for hint, network, status in zip(explicit_hints, networks, statuses):
        if hint:
            hints.append(hint)
            continue

        pieces = []
        if network:
            pieces.append(f"Originally aired on {network}")
        if status:
            pieces.append(f"Status: {status}")
        hints.append(". ".join(pieces))

    return pd.Series(hints, index=dataframe.index, dtype="object")


def load_catalog(csv_path: Path) -> pd.DataFrame:
    dataframe = pd.read_csv(csv_path)
    dataframe = _normalize_columns(dataframe)

    if "title" not in dataframe.columns:
        raise ValueError("Dataset is missing required column: title")

    dataframe["year"] = _derive_years(dataframe)
    if "content_type" not in dataframe.columns:
        if "release_date" in dataframe.columns and "first_air_date" not in dataframe.columns:
            dataframe["content_type"] = "Movie"
        else:
            dataframe["content_type"] = "Serial"
    dataframe["country"] = _first_non_empty(dataframe, "country", "origin_country")
    dataframe["language"] = _first_non_empty(dataframe, "language")
    dataframe["status"] = _first_non_empty(dataframe, "status")
    dataframe["status"] = dataframe["status"].where(dataframe["status"] != "", dataframe["content_type"].map(lambda value: "Released" if value == "Movie" else "Series"))
    dataframe["genres"] = _first_non_empty(dataframe, "genres")
    dataframe["themes"] = _first_non_empty(dataframe, "themes", "genres")
    dataframe["network"] = _first_non_empty(dataframe, "network", "production_company")
    dataframe["overview"] = _first_non_empty(dataframe, "overview")
    dataframe["cast"] = _first_non_empty(dataframe, "cast")
    dataframe["aliases"] = _build_aliases(dataframe)
    dataframe["keywords"] = _build_keywords(dataframe)
    dataframe["watch_hint"] = _build_watch_hints(dataframe)
    dataframe["poster_url"] = _first_non_empty(dataframe, "poster_url")

    # The bundled starter CSV is intentionally text-first. A few legacy poster
    # URLs in that seed file are placeholders that 404, so we prefer the app's
    # built-in poster cards until live TMDB enrichment is available.
    if csv_path.name == "dramas_seed.csv":
        dataframe["poster_url"] = ""

    for column in FINAL_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = ""

    for column in TEXT_COLUMNS:
        dataframe[column] = dataframe[column].map(_clean_text)

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


def load_combined_catalog(*csv_paths: Path) -> pd.DataFrame:
    datasets = []
    for csv_path in csv_paths:
        if csv_path and Path(csv_path).exists():
            datasets.append(load_catalog(Path(csv_path)))

    if not datasets:
        raise FileNotFoundError("No catalog files were found for the combined dataset.")

    combined = pd.concat(datasets, ignore_index=True)
    combined = combined.drop_duplicates(subset=["title", "year", "country", "content_type"]).reset_index(drop=True)
    return combined


def load_movies(csv_path: Path) -> pd.DataFrame:
    return load_catalog(csv_path)
