from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from difflib import SequenceMatcher
from urllib.parse import quote_plus

import requests


API_BASE_URL = "https://api.themoviedb.org/3"
FALLBACK_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/"
COUNTRY_NAMES = {
    "IN": "India",
    "PK": "Pakistan",
    "TR": "Turkey",
}


@dataclass(frozen=True)
class TMDBSettings:
    api_key: str = ""
    access_token: str = ""
    language: str = "en-US"
    timeout_seconds: int = 5

    @property
    def enabled(self) -> bool:
        return bool(self.api_key or self.access_token)


def _normalize_text(value: object) -> str:
    return " ".join(str(value).lower().split())


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


@lru_cache(maxsize=8)
def _cached_image_base_url(api_key: str, access_token: str, language: str, timeout_seconds: int) -> str:
    payload = _request(
        "/configuration",
        TMDBSettings(
            api_key=api_key,
            access_token=access_token,
            language=language,
            timeout_seconds=timeout_seconds,
        ),
    )
    if not payload:
        return f"{FALLBACK_IMAGE_BASE_URL}w500"

    images = payload.get("images", {})
    base_url = images.get("secure_base_url") or FALLBACK_IMAGE_BASE_URL
    poster_sizes = images.get("poster_sizes") or ["w500"]
    preferred_size = "w500" if "w500" in poster_sizes else poster_sizes[-1]
    return f"{base_url}{preferred_size}"


def get_image_base_url(settings: TMDBSettings) -> str:
    return _cached_image_base_url(
        settings.api_key,
        settings.access_token,
        settings.language,
        settings.timeout_seconds,
    )


def build_image_url(path: str | None, settings: TMDBSettings) -> str:
    if not path:
        return ""
    return f"{get_image_base_url(settings)}{path}"


def build_tmdb_search_url(query: str, media_type: str = "multi") -> str:
    path = "multi" if media_type == "multi" else media_type
    return f"https://www.themoviedb.org/search/{path}?query={quote_plus(query)}"


def _social_links(external_ids: dict | None) -> dict[str, str]:
    payload = external_ids or {}
    links: dict[str, str] = {}
    if payload.get("instagram_id"):
        links["Instagram"] = f"https://www.instagram.com/{payload['instagram_id']}/"
    if payload.get("twitter_id"):
        links["X"] = f"https://x.com/{payload['twitter_id']}"
    if payload.get("facebook_id"):
        links["Facebook"] = f"https://www.facebook.com/{payload['facebook_id']}"
    if payload.get("imdb_id"):
        links["IMDb"] = f"https://www.imdb.com/title/{payload['imdb_id']}/"
    return links


def _person_social_links(external_ids: dict | None) -> dict[str, str]:
    payload = external_ids or {}
    links: dict[str, str] = {}
    if payload.get("instagram_id"):
        links["Instagram"] = f"https://www.instagram.com/{payload['instagram_id']}/"
    if payload.get("twitter_id"):
        links["X"] = f"https://x.com/{payload['twitter_id']}"
    if payload.get("facebook_id"):
        links["Facebook"] = f"https://www.facebook.com/{payload['facebook_id']}"
    if payload.get("imdb_id"):
        links["IMDb"] = f"https://www.imdb.com/name/{payload['imdb_id']}/"
    if payload.get("tiktok_id"):
        links["TikTok"] = f"https://www.tiktok.com/@{payload['tiktok_id']}"
    return links


def _country_names(country_codes: list[str]) -> list[str]:
    return [COUNTRY_NAMES.get(code, code) for code in country_codes if code]


def _build_recommendation_cards(
    items: list[dict],
    settings: TMDBSettings,
    genres: list[str],
) -> list[dict]:
    recommendation_cards = []
    for item in items[:6]:
        recommendation_cards.append(
            {
                "title": item.get("name") or item.get("original_name") or "",
                "year": int((item.get("first_air_date") or "0")[:4] or 0),
                "overview": item.get("overview") or "",
                "country": ", ".join(_country_names(item.get("origin_country") or [])),
                "genres": ", ".join(genres[:2]) if genres else "Drama",
                "poster_url": build_image_url(item.get("poster_path"), settings),
                "tmdb_url": f"https://www.themoviedb.org/tv/{item.get('id')}",
            }
        )
    return recommendation_cards


def _build_tv_profile_payload(
    details: dict,
    credits: dict,
    recommendations: dict,
    settings: TMDBSettings,
    result: dict | None = None,
    source_label: str = "TMDB live",
) -> dict | None:
    seed = result or details or {}
    tv_id = details.get("id") or seed.get("id")
    if not tv_id:
        return None

    origin_country = details.get("origin_country") or seed.get("origin_country") or []
    genres = [genre.get("name", "") for genre in details.get("genres", []) if genre.get("name")]
    networks = [network.get("name", "") for network in details.get("networks", []) if network.get("name")]

    cast_entries = []
    for cast_member in credits.get("cast", [])[:16]:
        role = ""
        roles = cast_member.get("roles") or []
        if roles:
            role = roles[0].get("character", "")
        cast_entries.append(
            {
                "person_id": cast_member.get("id"),
                "name": cast_member.get("name", ""),
                "character": role,
                "episode_count": cast_member.get("total_episode_count", 0),
                "profile_url": build_image_url(cast_member.get("profile_path"), settings),
            }
        )

    social_links = _social_links(details.get("external_ids"))
    if details.get("homepage"):
        social_links["Official site"] = details["homepage"]

    country_names = _country_names(origin_country)
    first_air_date = details.get("first_air_date") or seed.get("first_air_date") or "0"
    return {
        "source": source_label,
        "tmdb_id": tv_id,
        "title": details.get("name") or seed.get("name") or seed.get("original_name") or "",
        "original_title": details.get("original_name") or seed.get("original_name") or "",
        "year": int(first_air_date[:4] or 0),
        "country": ", ".join(country_names),
        "country_codes": origin_country,
        "language": (details.get("spoken_languages") or [{}])[0].get("english_name")
        if details.get("spoken_languages")
        else details.get("original_language", "").upper(),
        "status": details.get("status") or "Series",
        "genres": genres,
        "themes": genres[:3],
        "network": ", ".join(networks),
        "overview": details.get("overview") or seed.get("overview") or "",
        "cast": cast_entries,
        "aliases": details.get("original_name") or seed.get("original_name") or "",
        "watch_hint": "Use the links below to check official listings and videos.",
        "poster_url": build_image_url(details.get("poster_path"), settings),
        "backdrop_url": build_image_url(details.get("backdrop_path"), settings),
        "tmdb_url": f"https://www.themoviedb.org/tv/{tv_id}",
        "social_links": social_links,
        "recommendations": _build_recommendation_cards(
            recommendations.get("results", []),
            settings=settings,
            genres=genres,
        ),
    }


def _pick_best_result(
    results: list[dict],
    query: str,
    preferred_country_code: str | None = None,
    year_range: tuple[int, int] | None = None,
) -> dict | None:
    if not results:
        return None

    normalized_query = _normalize_text(query)
    best_result = None
    best_score = -1.0
    for result in results:
        title = result.get("name") or result.get("original_name") or ""
        original_title = result.get("original_name") or ""
        first_air_date = result.get("first_air_date") or ""
        candidate_country_codes = result.get("origin_country") or []

        score = max(
            _normalize_text(title) == normalized_query and 3.5 or 0.0,
            _normalize_text(original_title) == normalized_query and 3.2 or 0.0,
        )
        score += _similarity(normalized_query, _normalize_text(title)) * 2
        score += _similarity(normalized_query, _normalize_text(original_title)) * 1.6
        if normalized_query in _normalize_text(title):
            score += 1.2
        if normalized_query in _normalize_text(original_title):
            score += 0.9
        if preferred_country_code and preferred_country_code in candidate_country_codes:
            score += 1.1
        if year_range and first_air_date:
            year = int(first_air_date[:4])
            if year_range[0] <= year <= year_range[1]:
                score += 0.6

        if score > best_score:
            best_score = score
            best_result = result

    return best_result


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _media_title(result: dict) -> str:
    return result.get("title") or result.get("name") or result.get("original_title") or result.get("original_name") or ""


def _media_original_title(result: dict) -> str:
    return result.get("original_title") or result.get("original_name") or _media_title(result)


def _media_year(result: dict) -> int:
    date_text = result.get("release_date") or result.get("first_air_date") or ""
    return int((date_text or "0")[:4] or 0)


def search_titles(
    query: str,
    settings: TMDBSettings,
    limit: int = 6,
) -> list[dict]:
    payload = _request(
        "/search/multi",
        settings,
        params={
            "query": query,
            "include_adult": "false",
            "page": 1,
        },
    )
    if not payload:
        return []

    image_base = get_image_base_url(settings)
    candidates: list[tuple[float, dict]] = []
    normalized_query = _normalize_text(query)
    for result in payload.get("results", []):
        media_type = result.get("media_type")
        if media_type not in {"movie", "tv"}:
            continue

        title = _media_title(result)
        score = _similarity(normalized_query, _normalize_text(title))
        if normalized_query == _normalize_text(title):
            score += 2.5
        elif normalized_query in _normalize_text(title):
            score += 1.2
        candidates.append((score, result))

    candidates.sort(key=lambda item: (item[0], _media_year(item[1])), reverse=True)
    matches: list[dict] = []
    for _, result in candidates[:limit]:
        media_type = result["media_type"]
        poster_path = result.get("poster_path") or ""
        matches.append(
            {
                "source": "TMDB live",
                "tmdb_id": result.get("id"),
                "content_type": "Movie" if media_type == "movie" else "Serial",
                "media_type": media_type,
                "title": _media_title(result),
                "original_title": _media_original_title(result),
                "year": _media_year(result),
                "country": ", ".join(_country_names(result.get("origin_country") or [])),
                "overview": result.get("overview") or "",
                "poster_url": f"{image_base}{poster_path}" if poster_path else "",
                "tmdb_url": f"https://www.themoviedb.org/{'movie' if media_type == 'movie' else 'tv'}/{result.get('id')}",
            }
        )
    return matches


def fetch_media_profile(tmdb_id: int, media_type: str, settings: TMDBSettings) -> dict | None:
    if media_type == "movie":
        details = _request(f"/movie/{tmdb_id}", settings, params={"append_to_response": "external_ids"}) or {}
        credits = _request(f"/movie/{tmdb_id}/credits", settings) or {}
        recommendations = _request(f"/movie/{tmdb_id}/recommendations", settings) or {}
        if not details:
            return None

        cast_entries = []
        for cast_member in credits.get("cast", [])[:12]:
            cast_entries.append(
                {
                    "person_id": cast_member.get("id"),
                    "name": cast_member.get("name", ""),
                    "character": cast_member.get("character", ""),
                    "profile_url": build_image_url(cast_member.get("profile_path"), settings),
                }
            )

        social_links = {}
        external_ids = details.get("external_ids") or {}
        if external_ids.get("imdb_id"):
            social_links["IMDb"] = f"https://www.imdb.com/title/{external_ids['imdb_id']}/"
        if details.get("homepage"):
            social_links["Official site"] = details["homepage"]

        recommendation_cards = []
        for item in recommendations.get("results", [])[:6]:
            recommendation_cards.append(
                {
                    "title": item.get("title") or item.get("original_title") or "",
                    "year": _media_year(item),
                    "overview": item.get("overview") or "",
                    "country": "",
                    "genres": ", ".join(genre.get("name", "") for genre in details.get("genres", [])[:2] if genre.get("name")),
                    "poster_url": build_image_url(item.get("poster_path"), settings),
                    "tmdb_url": f"https://www.themoviedb.org/movie/{item.get('id')}",
                    "content_type": "Movie",
                }
            )

        return {
            "source": "TMDB live",
            "tmdb_id": tmdb_id,
            "content_type": "Movie",
            "media_type": "movie",
            "title": details.get("title") or details.get("original_title") or "",
            "original_title": details.get("original_title") or details.get("title") or "",
            "year": _media_year(details),
            "country": ", ".join(country.get("name", "") for country in details.get("production_countries", []) if country.get("name")),
            "country_codes": [],
            "language": (details.get("spoken_languages") or [{}])[0].get("english_name")
            if details.get("spoken_languages")
            else details.get("original_language", "").upper(),
            "status": details.get("status") or "Released",
            "genres": [genre.get("name", "") for genre in details.get("genres", []) if genre.get("name")],
            "themes": [genre.get("name", "") for genre in details.get("genres", [])[:3] if genre.get("name")],
            "network": ", ".join(company.get("name", "") for company in details.get("production_companies", []) if company.get("name")),
            "overview": details.get("overview") or "",
            "cast": cast_entries,
            "aliases": details.get("original_title") or "",
            "watch_hint": "Use TMDB or YouTube search to find official streaming or trailer availability.",
            "poster_url": build_image_url(details.get("poster_path"), settings),
            "backdrop_url": build_image_url(details.get("backdrop_path"), settings),
            "tmdb_url": f"https://www.themoviedb.org/movie/{tmdb_id}",
            "social_links": social_links,
            "recommendations": recommendation_cards,
        }

    return _fetch_tv_profile_by_id(tmdb_id, settings)


def _fetch_tv_profile_by_id(tv_id: int, settings: TMDBSettings) -> dict | None:
    details = _request(f"/tv/{tv_id}", settings, params={"append_to_response": "external_ids"}) or {}
    credits = _request(f"/tv/{tv_id}/aggregate_credits", settings) or {}
    recommendations = _request(f"/tv/{tv_id}/recommendations", settings) or {}
    if not details:
        return None

    origin_country = details.get("origin_country") or []
    genres = [genre.get("name", "") for genre in details.get("genres", []) if genre.get("name")]
    networks = [network.get("name", "") for network in details.get("networks", []) if network.get("name")]
    cast_entries = []
    for cast_member in credits.get("cast", [])[:16]:
        role = ""
        roles = cast_member.get("roles") or []
        if roles:
            role = roles[0].get("character", "")
        cast_entries.append(
            {
                "person_id": cast_member.get("id"),
                "name": cast_member.get("name", ""),
                "character": role,
                "episode_count": cast_member.get("total_episode_count", 0),
                "profile_url": build_image_url(cast_member.get("profile_path"), settings),
            }
        )

    recommendation_cards = []
    for item in recommendations.get("results", [])[:6]:
        recommendation_cards.append(
            {
                "title": item.get("name") or item.get("original_name") or "",
                "year": _media_year(item),
                "overview": item.get("overview") or "",
                "country": ", ".join(_country_names(item.get("origin_country") or [])),
                "genres": ", ".join(genres[:2]) if genres else "Drama",
                "poster_url": build_image_url(item.get("poster_path"), settings),
                "tmdb_url": f"https://www.themoviedb.org/tv/{item.get('id')}",
                "content_type": "Serial",
            }
        )

    social_links = _social_links(details.get("external_ids"))
    if details.get("homepage"):
        social_links["Official site"] = details["homepage"]

    return {
        "source": "TMDB live",
        "tmdb_id": tv_id,
        "content_type": "Serial",
        "media_type": "tv",
        "title": details.get("name") or details.get("original_name") or "",
        "original_title": details.get("original_name") or details.get("name") or "",
        "year": _media_year(details),
        "country": ", ".join(_country_names(origin_country)),
        "country_codes": origin_country,
        "language": (details.get("spoken_languages") or [{}])[0].get("english_name")
        if details.get("spoken_languages")
        else details.get("original_language", "").upper(),
        "status": details.get("status") or "Series",
        "genres": genres,
        "themes": genres[:3],
        "network": ", ".join(networks),
        "overview": details.get("overview") or "",
        "cast": cast_entries,
        "aliases": details.get("original_name") or "",
        "watch_hint": "Use the links below to check official listings and videos.",
        "poster_url": build_image_url(details.get("poster_path"), settings),
        "backdrop_url": build_image_url(details.get("backdrop_path"), settings),
        "tmdb_url": f"https://www.themoviedb.org/tv/{tv_id}",
        "social_links": social_links,
        "recommendations": recommendation_cards,
    }


def search_tv_titles(
    query: str,
    settings: TMDBSettings,
    preferred_country_code: str | None = None,
    year_range: tuple[int, int] | None = None,
    limit: int = 8,
) -> list[dict]:
    params: dict[str, object] = {
        "query": query,
        "include_adult": "false",
        "page": 1,
    }
    if year_range and year_range[0] == year_range[1]:
        params["first_air_date_year"] = year_range[0]

    payload = _request("/search/tv", settings, params=params)
    if not payload:
        return []

    results: list[tuple[float, dict]] = []
    for result in payload.get("results", []):
        title = result.get("name") or result.get("original_name") or ""
        score = _similarity(_normalize_text(query), _normalize_text(title))
        if preferred_country_code and preferred_country_code in (result.get("origin_country") or []):
            score += 0.6
        results.append((score, result))

    results.sort(key=lambda item: item[0], reverse=True)
    image_base = get_image_base_url(settings)
    normalized: list[dict] = []
    for _, result in results[:limit]:
        tv_id = result.get("id")
        poster_path = result.get("poster_path") or ""
        normalized.append(
            {
                "tmdb_id": tv_id,
                "title": result.get("name") or result.get("original_name") or "",
                "original_title": result.get("original_name") or "",
                "overview": result.get("overview") or "",
                "first_air_date": result.get("first_air_date") or "",
                "year": int((result.get("first_air_date") or "0")[:4] or 0),
                "country_codes": result.get("origin_country") or [],
                "country_names": _country_names(result.get("origin_country") or []),
                "poster_url": f"{image_base}{poster_path}" if poster_path else "",
                "tmdb_url": f"https://www.themoviedb.org/tv/{tv_id}" if tv_id else build_tmdb_search_url(query),
            }
        )
    return normalized


def fetch_tv_profile(
    query: str,
    settings: TMDBSettings,
    preferred_country_code: str | None = None,
    year_range: tuple[int, int] | None = None,
) -> dict | None:
    payload = _request(
        "/search/tv",
        settings,
        params={
            "query": query,
            "include_adult": "false",
            "page": 1,
        },
    )
    if not payload:
        return None

    result = _pick_best_result(
        payload.get("results", []),
        query=query,
        preferred_country_code=preferred_country_code,
        year_range=year_range,
    )
    if not result:
        return None

    tv_id = result.get("id")
    details = _request(f"/tv/{tv_id}", settings, params={"append_to_response": "external_ids"}) or {}
    credits = _request(f"/tv/{tv_id}/aggregate_credits", settings) or {}
    recommendations = _request(f"/tv/{tv_id}/recommendations", settings) or {}
    return _build_tv_profile_payload(
        details=details,
        credits=credits,
        recommendations=recommendations,
        settings=settings,
        result=result,
        source_label="TMDB live",
    )


def fetch_tv_profile_by_id(tv_id: int, settings: TMDBSettings) -> dict | None:
    details = _request(f"/tv/{tv_id}", settings, params={"append_to_response": "external_ids"})
    if not details:
        return None

    credits = _request(f"/tv/{tv_id}/aggregate_credits", settings) or {}
    recommendations = _request(f"/tv/{tv_id}/recommendations", settings) or {}
    return _build_tv_profile_payload(
        details=details,
        credits=credits,
        recommendations=recommendations,
        settings=settings,
        result=details,
        source_label="TMDB starter match",
    )


def fetch_person_profile(person_id: int, settings: TMDBSettings) -> dict | None:
    details = _request(f"/person/{person_id}", settings, params={"append_to_response": "external_ids"})
    if not details:
        return None

    biography = details.get("biography") or ""
    short_bio = biography.split(". ")[0].strip()
    if short_bio and not short_bio.endswith("."):
        short_bio += "."
    if not short_bio:
        known_for = details.get("known_for_department") or "acting"
        short_bio = f"{details.get('name', 'This performer')} is known for {known_for.lower()}."

    return {
        "name": details.get("name", ""),
        "profile_url": build_image_url(details.get("profile_path"), settings),
        "known_for": details.get("known_for_department", ""),
        "short_bio": short_bio,
        "birthday": details.get("birthday", ""),
        "place_of_birth": details.get("place_of_birth", ""),
        "social_links": _person_social_links(details.get("external_ids")),
    }
