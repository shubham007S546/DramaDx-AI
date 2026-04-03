from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors


def _normalize_text(value: object) -> str:
    return " ".join(str(value).lower().replace("-", " ").split())


def _split_csv_text(value: object) -> list[str]:
    return [item.strip() for item in str(value).split(",") if item and item.strip()]


@dataclass
class DramaRecommender:
    max_features: int = 5000
    latent_dim: int = 50
    random_state: int = 42
    vectorizer: TfidfVectorizer = field(init=False)
    reducer: TruncatedSVD | None = field(default=None, init=False)
    neighbors: NearestNeighbors = field(init=False)
    catalog: pd.DataFrame = field(default_factory=pd.DataFrame, init=False)
    embeddings: Any = field(default=None, init=False)
    title_lookup: dict[str, int] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            max_features=self.max_features,
        )
        self.neighbors = NearestNeighbors(metric="cosine", algorithm="brute")

    def fit(self, catalog: pd.DataFrame) -> "DramaRecommender":
        self.catalog = catalog.reset_index(drop=True).copy()

        # Ensure country column is clean string
        # 🔥 FIX country column completely (handles list, None, etc.)
        self.catalog["country"] = self.catalog["country"].apply(
            lambda x: x[0] if isinstance(x, list) else x
        )
        
        self.catalog["country"] = (
            self.catalog["country"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        # Ensure feature_text exists; build it if missing
        if "feature_text" not in self.catalog.columns:
            self.catalog["feature_text"] = (
                self.catalog.get("title", pd.Series(dtype=str)).fillna("").astype(str) + " "
                + self.catalog.get("genres", pd.Series(dtype=str)).fillna("").astype(str) + " "
                + self.catalog.get("themes", pd.Series(dtype=str)).fillna("").astype(str) + " "
                + self.catalog.get("overview", pd.Series(dtype=str)).fillna("").astype(str) + " "
                + self.catalog.get("keywords", pd.Series(dtype=str)).fillna("").astype(str)
            )

        matrix = self.vectorizer.fit_transform(self.catalog["feature_text"])

        max_components = min(self.latent_dim, matrix.shape[0] - 1, matrix.shape[1] - 1)
        if max_components >= 2:
            self.reducer = TruncatedSVD(n_components=max_components, random_state=self.random_state)
            self.embeddings = self.reducer.fit_transform(matrix)
        else:
            self.reducer = None
            self.embeddings = matrix

        self.neighbors.fit(self.embeddings)
        self.title_lookup = {}
        for index, row in self.catalog.iterrows():
            self.title_lookup[_normalize_text(row["title"])] = index
            for alias in _split_csv_text(row.get("aliases", "")):
                self.title_lookup.setdefault(_normalize_text(alias), index)
        return self

    def _query_vector(self, index: int) -> Any:
        vector = self.embeddings[index]
        if hasattr(vector, "ndim") and getattr(vector, "ndim") == 1:
            return vector.reshape(1, -1)
        return vector

    def _filter_catalog(
        self,
        countries: list[str] | None = None,
        year_range: tuple[int, int] | None = None,
    ) -> pd.DataFrame:
        filtered = self.catalog.copy()

        # FIX: case-insensitive, strip-safe country matching
        if countries and len(countries) > 0:
            allowed = {c.strip().lower() for c in countries if c}
            if allowed:
                mask = filtered["country"].str.strip().str.lower().isin(allowed)
                filtered = filtered[mask]

        if year_range:
            start_year, end_year = year_range
            filtered = filtered[
                (filtered["year"] >= start_year) & (filtered["year"] <= end_year)
            ]

        return filtered.reset_index(drop=True)

    def available_titles(
        self,
        countries: list[str] | None = None,
        year_range: tuple[int, int] | None = None,
    ) -> list[str]:
        filtered = self._filter_catalog(countries=countries, year_range=year_range)
        if filtered.empty:
            return []
        return filtered.sort_values(["title", "year"])["title"].tolist()

    def search(
        self,
        query: str,
        countries: list[str] | None = None,
        year_range: tuple[int, int] | None = None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        filtered = self._filter_catalog(countries=countries, year_range=year_range)
        if filtered.empty:
            return []

        normalized_query = _normalize_text(query)
        if not normalized_query:
            return [
                row.to_dict()
                for _, row in filtered.sort_values(
                    ["year", "title"], ascending=[False, True]
                ).head(limit).iterrows()
            ]

        scored_rows: list[tuple[float, dict[str, Any]]] = []
        for _, row in filtered.iterrows():
            title_norm = _normalize_text(row["title"])
            alias_values = _split_csv_text(row.get("aliases", ""))
            alias_norms = [_normalize_text(alias) for alias in alias_values]
            overview_norm = _normalize_text(row.get("overview", ""))
            keywords_norm = _normalize_text(row.get("keywords", ""))

            ratio = max(
                [SequenceMatcher(None, normalized_query, title_norm).ratio()]
                + [SequenceMatcher(None, normalized_query, alias).ratio() for alias in alias_norms]
            )

            score = ratio

            if normalized_query == title_norm:
                score += 5.0
            elif normalized_query in title_norm:
                score += 2.5
            elif title_norm in normalized_query:
                score += 1.5

            if any(normalized_query == alias for alias in alias_norms):
                score += 2.0
            elif any(normalized_query in alias for alias in alias_norms):
                score += 1.2
            elif any(alias in normalized_query for alias in alias_norms if alias):
                score += 0.8

            # Word-level overlap boost (helps "ishq murshid" match "ishq e murshid")
            query_words = set(normalized_query.split())
            title_words = set(title_norm.split())
            overlap = query_words & title_words
            if overlap:
                score += 0.4 * len(overlap) / max(len(query_words), 1)

            if normalized_query in overview_norm or normalized_query in keywords_norm:
                score += 0.3

            row_dict = row.to_dict()
            row_dict["match_score"] = round(score, 4)
            scored_rows.append((score, row_dict))

        scored_rows.sort(key=lambda item: item[0], reverse=True)

        # FIX: lowered threshold 0.6 -> 0.35 so partial/word matches surface
        matches = [row for score, row in scored_rows if score >= 0.35]
        if not matches:
            return []
        return matches[:limit]

    def get_drama(self, title_or_alias: str) -> dict[str, Any]:
        lookup_key = _normalize_text(title_or_alias)
        if lookup_key in self.title_lookup:
            return self.catalog.iloc[self.title_lookup[lookup_key]].to_dict()

        matches = self.search(title_or_alias, limit=1)
        if not matches:
            raise KeyError(f"Drama '{title_or_alias}' was not found in the catalog.")
        return matches[0]

    def recommend(self, title_or_alias: str, top_n: int = 6) -> list[dict[str, Any]]:
        if self.catalog.empty:
            raise ValueError("The recommender has not been trained yet.")

        drama = self.get_drama(title_or_alias)
        lookup_key = _normalize_text(drama["title"])
        catalog_index = self.title_lookup.get(lookup_key)

        # FIX: graceful fallback if title not in lookup after get_drama
        if catalog_index is None:
            mask = self.catalog["title"].apply(_normalize_text) == lookup_key
            hits = self.catalog[mask]
            if hits.empty:
                return []
            catalog_index = int(hits.index[0])

        target_type = str(drama.get("content_type", "")).strip().lower()
        target_country = str(drama.get("country", "")).strip().lower()
        neighbor_count = min(top_n + 1, len(self.catalog))
        distances, indices = self.neighbors.kneighbors(
            self._query_vector(catalog_index),
            n_neighbors=neighbor_count,
        )

        recommendations: list[dict[str, Any]] = []
        for distance, index in zip(distances[0], indices[0]):
            if index == catalog_index:
                continue
            row = self.catalog.iloc[index]
            recommendations.append(
                {
                    **row.to_dict(),
                    "similarity": round(1 - float(distance), 4),
                    "_same_type": str(row.get("content_type", "")).strip().lower() == target_type,
                    "_same_country": str(row.get("country", "")).strip().lower() == target_country,
                }
            )

        recommendations.sort(
            key=lambda item: (
                item.get("_same_type", False),
                item.get("_same_country", False),
                item.get("similarity", 0.0),
            ),
            reverse=True,
        )
        for item in recommendations:
            item.pop("_same_type", None)
            item.pop("_same_country", None)
        return recommendations[:top_n]

    def save(self, artifact_path: Path) -> None:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, artifact_path)

    @classmethod
    def load(cls, artifact_path: Path) -> "DramaRecommender":
        return joblib.load(artifact_path)


MovieRecommender = DramaRecommender