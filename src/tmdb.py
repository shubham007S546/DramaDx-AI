from __future__ import annotations

from dataclasses import dataclass

import requests


API_BASE_URL = "https://api.themoviedb.org/3"
FALLBACK_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/"


@dataclass
class TMDBSettings:
    api_key: str = ""
    access_token: str = ""
    language: str = "en-US"
    timeout_seconds: int = 4

    @property
    def enabled(self) -> bool:
        return bool(self.api_key or self.access_token)


def _request(path: str, settings: TMDBSettings, params: dict | None = None) -> dict | None:
    if not settings.enabled:
        return None

    request_params = dict(params or {})
    request_params.setdefault("language", settings.language)
    headers: dict[str, str] = {}

    if settings.access_token:
        headers["Authorization"] = f"Bearer {settings.access_token}"
    elif settings.api_key:
        request_params["api_key"] = settings.api_key

    try:
        response = requests.get(
            f"{API_BASE_URL}{path}",
            params=request_params,
            headers=headers,
            timeout=settings.timeout_seconds,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None

    return response.json()


def get_image_base_url(settings: TMDBSettings) -> str:
    payload = _request("/configuration", settings)
    if not payload:
        return f"{FALLBACK_IMAGE_BASE_URL}w500"

    images = payload.get("images", {})
    base_url = images.get("secure_base_url") or FALLBACK_IMAGE_BASE_URL
    poster_sizes = images.get("poster_sizes") or ["w500"]

    preferred_size = "w500" if "w500" in poster_sizes else poster_sizes[-1]
    return f"{base_url}{preferred_size}"


def _pick_best_result(results: list[dict], title: str, year: int | None) -> dict | None:
    if not results:
        return None

    normalized_title = " ".join(title.lower().split())
    if year:
        for result in results:
            release_date = result.get("release_date", "")
            candidate_title = " ".join(result.get("title", "").lower().split())
            if candidate_title == normalized_title and release_date.startswith(str(year)):
                return result

    for result in results:
        candidate_title = " ".join(result.get("title", "").lower().split())
        if candidate_title == normalized_title:
            return result

    return results[0]


def fetch_movie_metadata(title: str, settings: TMDBSettings, year: int | None = None) -> dict | None:
    payload = _request(
        "/search/movie",
        settings,
        params={
            "query": title,
            "include_adult": "false",
        },
    )
    if not payload:
        return None

    result = _pick_best_result(payload.get("results", []), title, year)
    if not result:
        return None

    image_base_url = get_image_base_url(settings)
    poster_path = result.get("poster_path") or ""
    backdrop_path = result.get("backdrop_path") or ""
    movie_id = result.get("id")

    return {
        "tmdb_id": movie_id,
        "poster_url": f"{image_base_url}{poster_path}" if poster_path else "",
        "backdrop_url": f"{image_base_url}{backdrop_path}" if backdrop_path else "",
        "vote_average": result.get("vote_average"),
        "vote_count": result.get("vote_count"),
        "release_date": result.get("release_date", ""),
        "overview": result.get("overview", ""),
        "tmdb_url": f"https://www.themoviedb.org/movie/{movie_id}" if movie_id else "",
    }
