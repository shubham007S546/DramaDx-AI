from __future__ import annotations

from dataclasses import dataclass

import requests


SEARCH_API_URL = "https://www.googleapis.com/youtube/v3/search"


@dataclass(frozen=True)
class YouTubeSettings:
    api_key: str = ""
    region_code: str = "IN"
    timeout_seconds: int = 10

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


def _build_query(title: str, year: int | None = None) -> str:
    year_text = f" {year}" if year else ""
    return f"{title}{year_text} official trailer"


def _best_result(items: list[dict]) -> dict | None:
    if not items:
        return None

    preferred_keywords = ("official trailer", "trailer", "teaser")
    for keyword in preferred_keywords:
        for item in items:
            candidate_title = item.get("snippet", {}).get("title", "").lower()
            if keyword in candidate_title:
                return item
    return items[0]


def fetch_trailer(title: str, settings: YouTubeSettings, year: int | None = None) -> dict | None:
    if not settings.enabled:
        return None

    try:
        response = requests.get(
            SEARCH_API_URL,
            params={
                "key": settings.api_key,
                "part": "snippet",
                "q": _build_query(title, year),
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
    thumbnails = snippet.get("thumbnails", {})
    thumbnail = (
        thumbnails.get("high", {}).get("url")
        or thumbnails.get("medium", {}).get("url")
        or thumbnails.get("default", {}).get("url")
        or ""
    )
    if not video_id:
        return None

    return {
        "video_id": video_id,
        "title": snippet.get("title", ""),
        "description": snippet.get("description", ""),
        "channel_title": snippet.get("channelTitle", ""),
        "published_at": snippet.get("publishedAt", ""),
        "thumbnail_url": thumbnail,
        "watch_url": f"https://www.youtube.com/watch?v={video_id}",
        "embed_url": f"https://www.youtube.com/embed/{video_id}",
    }
