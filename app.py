from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from src.config import (
    APP_SUBTITLE,
    APP_TITLE,
    ARTIFACT_PATH,
    DATA_PATH,
    DEFAULT_TMDB_LANGUAGE,
    DEFAULT_YOUTUBE_REGION,
    MODEL_NAME,
    SUPPORTED_COUNTRIES,
    TMDB_FAQ_URL,
    TMDB_LOGO_GUIDE_URL,
    TMDB_LOGO_URL,
    TMDB_NOTICE,
    TMDB_SITE_URL,
    YOUTUBE_API_DOCS_URL,
    YOUTUBE_SITE_URL,
)
from src.data import load_catalog
from src.recommender import DramaRecommender
from src.tmdb import (
    TMDBSettings,
    build_tmdb_search_url,
    fetch_person_profile,
    fetch_tv_profile,
    search_tv_titles,
)
from src.youtube import YouTubeSettings, build_youtube_search_url, fetch_video_result


st.set_page_config(page_title=APP_TITLE, page_icon="🎭", layout="wide")

COUNTRY_CODE_MAP = {
    "India": "IN",
    "Pakistan": "PK",
    "Turkey": "TR",
}


def get_runtime_value(*names: str, default: str = "") -> str:
    for name in names:
        try:
            secret_value = st.secrets.get(name)
        except Exception:
            secret_value = None

        if secret_value not in (None, ""):
            return str(secret_value)

        env_value = os.getenv(name)
        if env_value not in (None, ""):
            return env_value

    return default


def split_tags(value: object) -> list[str]:
    return [part.strip() for part in str(value).split(",") if part and part.strip()]


def trim_text(value: str, limit: int = 220) -> str:
    cleaned = " ".join(str(value).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(1, 180, 228, 0.18), transparent 22%),
                linear-gradient(180deg, #f4f8fb 0%, #ffffff 45%, #f6fbff 100%);
        }
        .block-container {
            padding-top: 1.3rem;
            padding-bottom: 2.5rem;
        }
        .hero-panel {
            padding: 1.7rem 1.8rem;
            border-radius: 28px;
            background: linear-gradient(135deg, #081f34 0%, #0d253f 46%, #01b4e4 100%);
            color: #ffffff;
            box-shadow: 0 22px 44px rgba(13, 37, 63, 0.18);
        }
        .hero-panel h1 {
            margin: 0;
            font-size: 2.55rem;
            line-height: 1.05;
        }
        .hero-panel p {
            margin-top: 0.8rem;
            margin-bottom: 0;
            line-height: 1.65;
            max-width: 780px;
        }
        .chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin-top: 0.95rem;
        }
        .chip {
            display: inline-flex;
            align-items: center;
            padding: 0.35rem 0.72rem;
            border-radius: 999px;
            border: 1px solid rgba(255, 255, 255, 0.18);
            background: rgba(255, 255, 255, 0.13);
            font-size: 0.86rem;
        }
        .placeholder-card {
            min-height: 360px;
            display: flex;
            flex-direction: column;
            justify-content: flex-end;
            border-radius: 24px;
            padding: 1.1rem;
            background:
                linear-gradient(180deg, rgba(7, 20, 33, 0.10), rgba(7, 20, 33, 0.85)),
                linear-gradient(135deg, #0d253f 0%, #174566 56%, #01b4e4 100%);
            color: #ffffff;
            box-shadow: 0 18px 34px rgba(13, 37, 63, 0.18);
        }
        .placeholder-card .eyebrow {
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.76rem;
            opacity: 0.82;
        }
        .placeholder-card .title {
            margin-top: 0.4rem;
            font-size: 1.6rem;
            line-height: 1.1;
            font-weight: 700;
        }
        .soft-note {
            border: 1px solid rgba(13, 37, 63, 0.10);
            border-radius: 18px;
            padding: 1rem 1.05rem;
            background: rgba(255, 255, 255, 0.84);
            box-shadow: 0 14px 28px rgba(13, 37, 63, 0.06);
        }
        .tmdb-note {
            border: 1px solid rgba(1, 180, 228, 0.24);
            border-radius: 20px;
            padding: 1rem 1.1rem;
            background: rgba(1, 180, 228, 0.08);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def get_catalog(dataset_path: str):
    return load_catalog(Path(dataset_path))


@st.cache_resource(show_spinner=False)
def get_recommender(dataset_path: str, artifact_path: str) -> DramaRecommender:
    dataset = Path(dataset_path)
    artifact = Path(artifact_path)

    if artifact.exists() and artifact.stat().st_mtime >= dataset.stat().st_mtime:
        try:
            return DramaRecommender.load(artifact)
        except Exception:
            pass

    recommender = DramaRecommender().fit(load_catalog(dataset))
    try:
        recommender.save(artifact)
    except Exception:
        pass
    return recommender


@st.cache_data(show_spinner=False, ttl=3600)
def get_live_profile_cached(
    query: str,
    api_key: str,
    access_token: str,
    language: str,
    preferred_country_code: str | None,
    start_year: int,
    end_year: int,
):
    settings = TMDBSettings(api_key=api_key, access_token=access_token, language=language)
    return fetch_tv_profile(
        query=query,
        settings=settings,
        preferred_country_code=preferred_country_code,
        year_range=(start_year, end_year),
    )


@st.cache_data(show_spinner=False, ttl=3600)
def get_live_search_results_cached(
    query: str,
    api_key: str,
    access_token: str,
    language: str,
    preferred_country_code: str | None,
    start_year: int,
    end_year: int,
):
    settings = TMDBSettings(api_key=api_key, access_token=access_token, language=language)
    return search_tv_titles(
        query=query,
        settings=settings,
        preferred_country_code=preferred_country_code,
        year_range=(start_year, end_year),
        limit=5,
    )


@st.cache_data(show_spinner=False, ttl=3600)
def get_person_profile_cached(person_id: int, api_key: str, access_token: str, language: str):
    settings = TMDBSettings(api_key=api_key, access_token=access_token, language=language)
    return fetch_person_profile(person_id=person_id, settings=settings)


@st.cache_data(show_spinner=False, ttl=3600)
def get_watch_video_cached(title: str, country: str, api_key: str, region_code: str):
    settings = YouTubeSettings(api_key=api_key, region_code=region_code)
    return fetch_video_result(title=title, country=country, settings=settings, mode="watch")


def build_tmdb_settings() -> TMDBSettings:
    st.sidebar.header("Live Data")
    language_options = ["en-US", "hi-IN"]
    configured_language = get_runtime_value("TMDB_LANGUAGE", default=DEFAULT_TMDB_LANGUAGE)
    default_language = configured_language if configured_language in language_options else "en-US"

    with st.sidebar.expander("Session-only TMDB credentials", expanded=False):
        runtime_api_key = st.text_input(
            "TMDB API Key",
            type="password",
            key="runtime_tmdb_api_key",
            help="Optional session input if you do not want to edit .env.",
        )
        runtime_access_token = st.text_input(
            "TMDB Bearer Token",
            type="password",
            key="runtime_tmdb_access_token",
            help="Preferred option for live TV drama search and details.",
        )

    api_key = runtime_api_key.strip() or get_runtime_value("TMDB_API_KEY")
    access_token = runtime_access_token.strip() or get_runtime_value("TMDB_BEARER_TOKEN", "TMDB_ACCESS_TOKEN")
    language = st.sidebar.selectbox("TMDB Language", options=language_options, index=language_options.index(default_language))
    return TMDBSettings(api_key=api_key, access_token=access_token, language=language)


def build_youtube_settings() -> YouTubeSettings:
    region_options = ["IN", "PK", "TR", "US", "GB"]
    configured_region = get_runtime_value("YOUTUBE_REGION_CODE", default=DEFAULT_YOUTUBE_REGION)
    default_region = configured_region if configured_region in region_options else "IN"

    with st.sidebar.expander("Session-only YouTube key", expanded=False):
        runtime_api_key = st.text_input(
            "YouTube API Key",
            type="password",
            key="runtime_youtube_api_key",
            help="Optional session input for official video lookups.",
        )

    api_key = runtime_api_key.strip() or get_runtime_value("YOUTUBE_API_KEY")
    region_code = st.sidebar.selectbox("YouTube Region", options=region_options, index=region_options.index(default_region))
    return YouTubeSettings(api_key=api_key, region_code=region_code)


def render_sidebar_summary(tmdb_settings: TMDBSettings, youtube_settings: YouTubeSettings) -> None:
    st.sidebar.divider()
    st.sidebar.markdown("### Status")
    if tmdb_settings.enabled:
        st.sidebar.success("TMDB live TV search is ready.")
    else:
        st.sidebar.warning("TMDB credentials are missing, so the app will use the starter drama catalog only.")

    if youtube_settings.enabled:
        st.sidebar.success("YouTube matching is ready.")
    else:
        st.sidebar.info("YouTube key is optional. Without it, the app will still show direct search links.")

    st.sidebar.caption("Keys stay private. Use local .env, Streamlit secrets, or the session-only inputs above.")


def create_local_profile(record: dict) -> dict:
    cast_entries = [{"name": name, "character": "", "person_id": None, "profile_url": ""} for name in split_tags(record.get("cast", ""))]
    return {
        "source": "Starter catalog",
        "title": record["title"],
        "original_title": record["title"],
        "year": int(record["year"]),
        "country": record.get("country", ""),
        "country_codes": [COUNTRY_CODE_MAP.get(record.get("country", ""), "")],
        "language": record.get("language", ""),
        "status": record.get("status", ""),
        "genres": split_tags(record.get("genres", "")),
        "themes": split_tags(record.get("themes", "")),
        "network": record.get("network", ""),
        "overview": record.get("overview", ""),
        "aliases": record.get("aliases", ""),
        "watch_hint": record.get("watch_hint", ""),
        "poster_url": record.get("poster_url", ""),
        "backdrop_url": "",
        "tmdb_url": build_tmdb_search_url(record["title"]),
        "social_links": {},
        "cast": cast_entries,
        "recommendations": [],
    }


def render_placeholder_poster(title: str, country: str, year: int) -> None:
    st.markdown(
        f"""
        <div class="placeholder-card">
          <div class="eyebrow">{country or "Drama"} • {year}</div>
          <div class="title">{title}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_match_summary(local_matches: list[dict], live_matches: list[dict]) -> None:
    if local_matches:
        st.markdown("#### Starter catalog matches")
        for match in local_matches[:4]:
            st.caption(f"{match['title']} • {match['country']} • {match['year']} • match {match.get('match_score', 0):.2f}")

    if live_matches:
        st.markdown("#### TMDB live matches")
        for match in live_matches[:4]:
            country = ", ".join(match.get("country_names", [])) or "Unknown"
            year = match.get("year") or "-"
            st.caption(f"{match['title']} • {country} • {year}")


def render_profile_header(profile: dict) -> None:
    st.markdown(
        f"""
        <div class="hero-panel">
          <p style="margin: 0; text-transform: uppercase; letter-spacing: 0.08em; opacity: 0.78;">Drama discovery workspace</p>
          <h1>{APP_TITLE}</h1>
          <p>{APP_SUBTITLE}</p>
          <div class="chip-row">
            <span class="chip">{profile.get('source', 'Profile loaded')}</span>
            <span class="chip">{profile.get('country', 'Country unknown')}</span>
            <span class="chip">{profile.get('status', 'Series')}</span>
            <span class="chip">{profile.get('year', 'Year unknown')}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_profile_links(profile: dict, youtube_settings: YouTubeSettings) -> None:
    watch_query = f"{profile['title']} official drama"
    link_specs = [
        ("TMDB Search", build_tmdb_search_url(profile["title"])),
        ("YouTube Search", build_youtube_search_url(watch_query)),
    ]
    if profile.get("tmdb_url"):
        link_specs.insert(0, ("TMDB Page", profile["tmdb_url"]))

    social_links = profile.get("social_links", {})
    for name in ("Instagram", "Official site", "IMDb", "Facebook", "X"):
        if name in social_links:
            link_specs.append((name, social_links[name]))

    video = None
    if youtube_settings.enabled:
        video = get_watch_video_cached(
            title=profile["title"],
            country=profile.get("country", ""),
            api_key=youtube_settings.api_key,
            region_code=youtube_settings.region_code,
        )
        if video and video.get("watch_url"):
            link_specs.insert(0, ("Best YouTube Match", video["watch_url"]))

    rendered = set()
    columns = st.columns(min(4, max(1, len(link_specs[:4]))))
    for index, (label, url) in enumerate(link_specs[:4]):
        if not url or (label, url) in rendered:
            continue
        rendered.add((label, url))
        with columns[index % len(columns)]:
            st.link_button(label, url, use_container_width=True)

    if video and video.get("watch_url"):
        with st.expander("Preview YouTube result", expanded=False):
            st.video(video["watch_url"])
            st.caption(f"{video.get('title', 'Video')} • {video.get('channel_title', 'YouTube')}")


def render_profile(profile: dict, tmdb_settings: TMDBSettings, youtube_settings: YouTubeSettings) -> None:
    poster_column, content_column = st.columns([0.85, 1.4])

    with poster_column:
        if profile.get("poster_url"):
            st.image(profile["poster_url"], use_container_width=True)
        else:
            render_placeholder_poster(profile["title"], profile.get("country", ""), int(profile.get("year", 0) or 0))

    with content_column:
        st.subheader(f"{profile['title']} ({profile.get('year', 'Unknown')})")
        meta_items = [
            profile.get("country", ""),
            profile.get("language", ""),
            profile.get("status", ""),
            profile.get("network", ""),
        ]
        st.caption(" • ".join([item for item in meta_items if item]))
        st.write(profile.get("overview") or "No summary is available yet for this title.")

        if profile.get("themes"):
            st.markdown("**Main themes**")
            st.write(", ".join(profile["themes"]))

        if profile.get("genres"):
            st.markdown("**Genres**")
            st.write(", ".join(profile["genres"]))

        if profile.get("aliases"):
            st.markdown("**Also searched as**")
            st.write(profile["aliases"])

        if profile.get("watch_hint"):
            st.info(profile["watch_hint"])

        render_profile_links(profile, youtube_settings)

        if not tmdb_settings.enabled and not profile.get("poster_url"):
            st.warning("Real posters, richer cast, and social handles need TMDB credentials in .env or the session-only sidebar inputs.")


def render_cast_explorer(profile: dict, tmdb_settings: TMDBSettings) -> None:
    cast = profile.get("cast", [])
    if not cast:
        st.info("No cast data is available for this title yet.")
        return

    st.markdown("### Cast")
    cast_columns = st.columns(4)
    for index, member in enumerate(cast[:8]):
        with cast_columns[index % 4]:
            with st.container(border=True):
                if member.get("profile_url"):
                    st.image(member["profile_url"], use_container_width=True)
                st.markdown(f"**{member.get('name', 'Cast member')}**")
                if member.get("character"):
                    st.caption(member["character"])

    labels = []
    member_lookup: dict[str, dict] = {}
    for member in cast[:12]:
        label = member.get("name", "Cast member")
        if member.get("character"):
            label = f"{label} — {member['character']}"
        labels.append(label)
        member_lookup[label] = member

    selected_label = st.selectbox("Actor quick profile", options=labels)
    selected_member = member_lookup[selected_label]
    live_person = None
    if tmdb_settings.enabled and selected_member.get("person_id"):
        live_person = get_person_profile_cached(
            person_id=int(selected_member["person_id"]),
            api_key=tmdb_settings.api_key,
            access_token=tmdb_settings.access_token,
            language=tmdb_settings.language,
        )

    info_column, image_column = st.columns([1.35, 0.65])
    with info_column:
        st.markdown(f"**{selected_member.get('name', 'Cast member')}**")
        if selected_member.get("character"):
            st.caption(f"Role: {selected_member['character']}")

        if live_person:
            st.write(live_person.get("short_bio", "Biography unavailable."))
            extras = [live_person.get("known_for", ""), live_person.get("place_of_birth", "")]
            extras = [extra for extra in extras if extra]
            if extras:
                st.caption(" • ".join(extras))
            if live_person.get("social_links"):
                social_columns = st.columns(min(3, len(live_person["social_links"])))
                for index, (label, url) in enumerate(live_person["social_links"].items()):
                    with social_columns[index % len(social_columns)]:
                        st.link_button(label, url, key=f"person_social_{selected_member.get('name')}_{label}", use_container_width=True)
        else:
            st.write(
                f"{selected_member.get('name', 'This actor')} is part of the main cast for {profile['title']}. "
                "Add TMDB credentials to unlock a short biography and social handles."
            )

    with image_column:
        if live_person and live_person.get("profile_url"):
            st.image(live_person["profile_url"], use_container_width=True)


def render_recommendations(
    profile: dict,
    recommender: DramaRecommender,
    fallback_title: str,
    selected_countries: list[str],
    year_range: tuple[int, int],
) -> None:
    live_recommendations = profile.get("recommendations") or []
    if live_recommendations:
        recommendations = live_recommendations[:6]
        source_label = "TMDB live recommendations"
    else:
        recommendations = recommender.recommend(fallback_title, top_n=6)
        source_label = "Starter catalog recommendations"

    st.markdown(f"### Similar dramas")
    st.caption(source_label)
    columns = st.columns(3)
    for index, recommendation in enumerate(recommendations):
        with columns[index % 3]:
            with st.container(border=True):
                if recommendation.get("poster_url"):
                    st.image(recommendation["poster_url"], use_container_width=True)
                else:
                    render_placeholder_poster(
                        recommendation.get("title", "Recommendation"),
                        recommendation.get("country", ""),
                        int(recommendation.get("year", 0) or 0),
                    )

                st.markdown(f"**{recommendation.get('title', 'Unknown title')}**")
                caption_parts = []
                if recommendation.get("country"):
                    caption_parts.append(recommendation["country"])
                if recommendation.get("year"):
                    caption_parts.append(str(recommendation["year"]))
                if recommendation.get("similarity") is not None:
                    caption_parts.append(f"match {recommendation['similarity']:.0%}")
                st.caption(" • ".join(caption_parts))
                st.write(trim_text(recommendation.get("overview", "No summary available.")))

                tmdb_link = recommendation.get("tmdb_url") or build_tmdb_search_url(recommendation.get("title", ""))
                youtube_link = build_youtube_search_url(f"{recommendation.get('title', '')} official drama")
                st.link_button(
                    "Open TMDB",
                    tmdb_link,
                    key=f"tmdb_link_{recommendation.get('title', '')}_{index}",
                    use_container_width=True,
                )
                st.link_button(
                    "Search YouTube",
                    youtube_link,
                    key=f"yt_link_{recommendation.get('title', '')}_{index}",
                    use_container_width=True,
                )


def render_search_tab(
    catalog,
    recommender: DramaRecommender,
    tmdb_settings: TMDBSettings,
    youtube_settings: YouTubeSettings,
) -> None:
    render_profile_header(
        {
            "source": "Starter catalog and TMDB live search",
            "country": "India • Pakistan • Turkey",
            "status": MODEL_NAME,
            "year": "2020-2026",
        }
    )

    min_year = int(catalog["year"].min())
    max_year = max(2026, int(catalog["year"].max()))

    filter_column, query_column = st.columns([0.95, 1.25])
    with filter_column:
        selected_countries = st.multiselect(
            "Countries",
            options=list(SUPPORTED_COUNTRIES),
            default=list(SUPPORTED_COUNTRIES),
        )
        year_range = st.slider(
            "Year range",
            min_value=min_year,
            max_value=max_year,
            value=(max(2020, min_year), max_year),
        )

    with query_column:
        query = st.text_input(
            "Search a drama title",
            placeholder="Try Tere Bin, Ishq Murshid, Yargi, Heeramandi, or your own spelling",
        ).strip()
        fallback_titles = recommender.available_titles(countries=selected_countries, year_range=year_range)
        default_fallback = fallback_titles[0] if fallback_titles else catalog.iloc[0]["title"]
        fallback_title = st.selectbox("Starter catalog fallback", options=fallback_titles or [default_fallback])

    preferred_country_code = COUNTRY_CODE_MAP[selected_countries[0]] if len(selected_countries) == 1 else None
    local_matches = recommender.search(query, countries=selected_countries, year_range=year_range, limit=5) if query else []
    live_matches = []
    live_profile = None
    if query and tmdb_settings.enabled:
        live_matches = get_live_search_results_cached(
            query=query,
            api_key=tmdb_settings.api_key,
            access_token=tmdb_settings.access_token,
            language=tmdb_settings.language,
            preferred_country_code=preferred_country_code,
            start_year=year_range[0],
            end_year=year_range[1],
        )
        live_profile = get_live_profile_cached(
            query=query,
            api_key=tmdb_settings.api_key,
            access_token=tmdb_settings.access_token,
            language=tmdb_settings.language,
            preferred_country_code=preferred_country_code,
            start_year=year_range[0],
            end_year=year_range[1],
        )

    if query:
        render_match_summary(local_matches, live_matches)

    if query and live_profile:
        profile = live_profile
        local_fallback = local_matches[0]["title"] if local_matches else fallback_title
    else:
        profile = create_local_profile(recommender.get_drama(local_matches[0]["title"] if local_matches else fallback_title))
        local_fallback = profile["title"]
        if query and not tmdb_settings.enabled:
            st.info("TMDB is not configured yet, so the app is showing the closest starter catalog drama instead of a live search result.")
        elif query and tmdb_settings.enabled and not live_profile:
            st.warning("TMDB did not return a matching live drama for this search, so the starter catalog result is shown.")

    render_profile(profile, tmdb_settings, youtube_settings)
    render_cast_explorer(profile, tmdb_settings)
    render_recommendations(profile, recommender, local_fallback, selected_countries, year_range)


def render_catalog_tab(catalog) -> None:
    st.markdown("### Starter drama catalog")
    st.caption("This offline catalog keeps the app useful before live keys are added. Replace or expand it later with your full ETL output.")

    query = st.text_input("Filter the starter catalog", placeholder="Search title, cast, network, or keywords", key="catalog_query").strip()
    selected_countries = st.multiselect(
        "Catalog countries",
        options=list(SUPPORTED_COUNTRIES),
        default=list(SUPPORTED_COUNTRIES),
        key="catalog_countries",
    )

    filtered = catalog.copy()
    if query:
        search_text = filtered[["title", "country", "network", "cast", "aliases", "overview", "keywords"]].fillna("").agg(" ".join, axis=1)
        filtered = filtered[search_text.str.contains(query, case=False, na=False)]

    if selected_countries:
        filtered = filtered[filtered["country"].isin(selected_countries)]

    filtered = filtered.sort_values(["country", "year", "title"], ascending=[True, False, True])
    st.metric("Visible dramas", int(len(filtered)))
    st.dataframe(
        filtered[["title", "country", "year", "language", "status", "network", "genres", "cast"]],
        use_container_width=True,
        hide_index=True,
    )


def render_setup_tab(tmdb_settings: TMDBSettings, youtube_settings: YouTubeSettings) -> None:
    st.markdown("### Setup and source status")
    left_column, right_column = st.columns([1.1, 1])

    with left_column:
        st.markdown(
            f"""
            <div class="tmdb-note">
              <p><strong>TMDB attribution notice</strong></p>
              <p>{TMDB_NOTICE}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.image(TMDB_LOGO_URL, width=120)

        with st.container(border=True):
            st.markdown("#### Why posters or live links may be missing")
            st.write("The starter catalog ships with text data only. Real posters, richer cast details, TMDB links, and actor biographies need a TMDB token.")
            st.write("You can keep keys private by using local .env, Streamlit secrets, or the session-only sidebar inputs.")

        with st.container(border=True):
            st.markdown("#### Recommended next dataset step")
            st.write("Use this app as the UI shell, then build your full ETL pipeline to replace the starter catalog with 2020-2026 TV serial data.")
            st.write("The local recommender artifact will retrain automatically when the CSV changes.")

    with right_column:
        with st.container(border=True):
            st.markdown("#### Current key status")
            st.metric("TMDB live TV search", "Ready" if tmdb_settings.enabled else "Missing key")
            st.metric("YouTube lookup", "Ready" if youtube_settings.enabled else "Optional")

        with st.container(border=True):
            st.markdown("#### Official links")
            st.link_button("TMDB website", TMDB_SITE_URL, use_container_width=True)
            st.link_button("TMDB FAQ", TMDB_FAQ_URL, use_container_width=True)
            st.link_button("TMDB attribution guide", TMDB_LOGO_GUIDE_URL, use_container_width=True)
            st.link_button("YouTube Data API docs", YOUTUBE_API_DOCS_URL, use_container_width=True)
            st.link_button("YouTube", YOUTUBE_SITE_URL, use_container_width=True)


def main() -> None:
    inject_styles()
    tmdb_settings = build_tmdb_settings()
    youtube_settings = build_youtube_settings()
    render_sidebar_summary(tmdb_settings, youtube_settings)

    catalog = get_catalog(str(DATA_PATH))
    recommender = get_recommender(str(DATA_PATH), str(ARTIFACT_PATH))

    search_tab, catalog_tab, setup_tab = st.tabs(["Search", "Catalog", "Setup"])
    with search_tab:
        render_search_tab(catalog, recommender, tmdb_settings, youtube_settings)
    with catalog_tab:
        render_catalog_tab(catalog)
    with setup_tab:
        render_setup_tab(tmdb_settings, youtube_settings)


if __name__ == "__main__":
    main()
