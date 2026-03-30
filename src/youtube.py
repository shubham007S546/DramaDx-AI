from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus

import requests


SEARCH_API_URL = "https://www.googleapis.com/youtube/v3/search"


@dataclass(frozen=True)
class YouTubeSettings:
    api_key: str = ""
    region_code: str = "IN"
    timeout_seconds: int = 8

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


def build_youtube_search_url(query: str) -> str:
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"


def _build_query(title: str, country: str = "", mode: str = "watch") -> str:
    if mode == "watch":
        suffix = "official drama full episode"
    else:
        suffix = "official trailer"
    country_text = f" {country}" if country else ""
    return f"{title}{country_text} {suffix}".strip()


def _best_result(items: list[dict]) -> dict | None:
    if not items:
        return None

    preferred_keywords = ("full episode", "official", "trailer", "teaser")
    for keyword in preferred_keywords:
        for item in items:
            candidate_title = item.get("snippet", {}).get("title", "").lower()
            if keyword in candidate_title:
                return item
    return items[0]


def fetch_video_result(title: str, settings: YouTubeSettings, country: str = "", mode: str = "watch") -> dict | None:
    if not settings.enabled:
        return None

    try:
        response = requests.get(
            SEARCH_API_URL,
            params={
                "key": settings.api_key,
                "part": "snippet",
                "q": _build_query(title, country=country, mode=mode),
                "type": "video",
                "videoEmbeddable": "true",
                "maxResults": 5,
                "regionCode": settings.region_code,
            },
            timeout=settings.timeout_seconds,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None

    payload = response.json()
    result = _best_result(payload.get("items", []))
    if not result:
        return None

    video_id = result.get("id", {}).get("videoId")
    snippet = result.get("snippet", {})
    if not video_id:
        return None

    thumbnails = snippet.get("thumbnails", {})
    thumbnail = (
        thumbnails.get("high", {}).get("url")
        or thumbnails.get("medium", {}).get("url")
        or thumbnails.get("default", {}).get("url")
        or ""
    )
    return {
        "video_id": video_id,
        "title": snippet.get("title", ""),
        "channel_title": snippet.get("channelTitle", ""),
        "thumbnail_url": thumbnail,
        "watch_url": f"https://www.youtube.com/watch?v={video_id}",
        "embed_url": f"https://www.youtube.com/embed/{video_id}",
    }


def fetch_trailer(title: str, settings: YouTubeSettings, year: int | None = None) -> dict | None:
    _ = year
    return fetch_video_result(title=title, settings=settings, mode="trailer")
