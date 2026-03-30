from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors


def _normalize_title(title: str) -> str:
    return " ".join(str(title).lower().split())


@dataclass
class MovieRecommender:
    max_features: int = 4000
    latent_dim: int = 50
    random_state: int = 42
    vectorizer: TfidfVectorizer = field(init=False)
    reducer: TruncatedSVD | None = field(default=None, init=False)
    neighbors: NearestNeighbors = field(init=False)
    movies: pd.DataFrame = field(default_factory=pd.DataFrame, init=False)
    embeddings: Any = field(default=None, init=False)
    title_lookup: dict[str, int] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            max_features=self.max_features,
        )
        self.neighbors = NearestNeighbors(metric="cosine", algorithm="brute")

    def fit(self, movies: pd.DataFrame) -> "MovieRecommender":
        self.movies = movies.reset_index(drop=True).copy()
        matrix = self.vectorizer.fit_transform(self.movies["feature_text"])

        max_components = min(self.latent_dim, matrix.shape[0] - 1, matrix.shape[1] - 1)
        if max_components >= 2:
            self.reducer = TruncatedSVD(n_components=max_components, random_state=self.random_state)
            self.embeddings = self.reducer.fit_transform(matrix)
        else:
            self.reducer = None
            self.embeddings = matrix

        self.neighbors.fit(self.embeddings)
        self.title_lookup = {
            _normalize_title(title): index for index, title in enumerate(self.movies["title"].tolist())
        }
        return self

    def available_titles(self) -> list[str]:
        return self.movies["title"].sort_values().tolist()

    def _query_vector(self, movie_index: int) -> Any:
        vector = self.embeddings[movie_index]
        if hasattr(vector, "ndim") and getattr(vector, "ndim") == 1:
            return vector.reshape(1, -1)
        return vector

    def recommend(self, title: str, top_n: int = 5) -> list[dict[str, Any]]:
        if self.movies.empty:
            raise ValueError("The recommender has not been trained yet.")

        lookup_key = _normalize_title(title)
        if lookup_key not in self.title_lookup:
            raise KeyError(f"Movie '{title}' was not found in the catalog.")

        movie_index = self.title_lookup[lookup_key]
        neighbor_count = min(top_n + 1, len(self.movies))
        distances, indices = self.neighbors.kneighbors(
            self._query_vector(movie_index),
            n_neighbors=neighbor_count,
        )

        recommendations: list[dict[str, Any]] = []
        for distance, index in zip(distances[0], indices[0]):
            if index == movie_index:
                continue

            row = self.movies.iloc[index]
            recommendations.append(
                {
                    "title": row["title"],
                    "year": int(row["year"]),
                    "genres": row["genres"],
                    "keywords": row["keywords"],
                    "overview": row["overview"],
                    "director": row.get("director", ""),
                    "similarity": round(1 - float(distance), 4),
                }
            )

        return recommendations[:top_n]

    def get_movie(self, title: str) -> dict[str, Any]:
        lookup_key = _normalize_title(title)
        if lookup_key not in self.title_lookup:
            raise KeyError(f"Movie '{title}' was not found in the catalog.")
        return self.movies.iloc[self.title_lookup[lookup_key]].to_dict()

    def save(self, artifact_path: Path) -> None:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, artifact_path)

    @classmethod
    def load(cls, artifact_path: Path) -> "MovieRecommender":
        return joblib.load(artifact_path)
