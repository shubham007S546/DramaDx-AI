from __future__ import annotations

import os
import random
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


def ensure_ui_state(catalog) -> None:
    if "watchlist" not in st.session_state:
        st.session_state["watchlist"] = []
    if "search_query" not in st.session_state:
        st.session_state["search_query"] = ""
    if "search_countries" not in st.session_state:
        st.session_state["search_countries"] = list(SUPPORTED_COUNTRIES)
    if "search_year_range" not in st.session_state:
        st.session_state["search_year_range"] = (
            max(2020, int(catalog["year"].min())),
            max(2026, int(catalog["year"].max())),
        )
    if "home_query" not in st.session_state:
        st.session_state["home_query"] = ""
    if "use_tmdb" not in st.session_state:
        st.session_state["use_tmdb"] = False
    if "use_youtube" not in st.session_state:
        st.session_state["use_youtube"] = False


def set_search_context(title: str, country: str = "") -> None:
    st.session_state["search_query"] = title
    if country in SUPPORTED_COUNTRIES:
        st.session_state["search_countries"] = [country]


def add_watchlist_entry(entry: dict) -> None:
    watchlist = st.session_state.setdefault("watchlist", [])
    key = (
        str(entry.get("title", "")).strip().lower(),
        str(entry.get("country", "")).strip().lower(),
        int(entry.get("year", 0) or 0),
    )
    existing_keys = {
        (
            str(item.get("title", "")).strip().lower(),
            str(item.get("country", "")).strip().lower(),
            int(item.get("year", 0) or 0),
        )
        for item in watchlist
    }
    if key not in existing_keys:
        watchlist.append(entry)


def build_watchlist_entry(profile: dict, fallback_title: str = "") -> dict:
    return {
        "title": profile.get("title") or fallback_title,
        "country": profile.get("country", ""),
        "year": int(profile.get("year", 0) or 0),
        "source": profile.get("source", "Saved"),
        "poster_url": profile.get("poster_url", ""),
        "tmdb_url": profile.get("tmdb_url", ""),
        "overview": profile.get("overview", ""),
        "search_title": fallback_title or profile.get("title", ""),
    }


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 2rem;
        }
        .hero-panel {
            padding: 1rem 0 0.5rem 0;
        }
        .hero-panel h1 {
            margin: 0 0 0.35rem 0;
            font-size: 2.1rem;
        }
        .hero-panel p {
            margin: 0.35rem 0 0 0;
        }
        .chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
            margin-top: 0.7rem;
        }
        .chip {
            display: inline-flex;
            align-items: center;
            padding: 0.25rem 0.6rem;
            border-radius: 999px;
            border: 1px solid rgba(128, 128, 128, 0.35);
            font-size: 0.86rem;
        }
        .placeholder-card {
            min-height: 180px;
            border-radius: 16px;
            padding: 1rem;
            border: 1px dashed rgba(128, 128, 128, 0.45);
        }
        .placeholder-card .eyebrow {
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.76rem;
            opacity: 0.8;
        }
        .placeholder-card .title {
            margin-top: 0.4rem;
            font-size: 1.35rem;
            line-height: 1.1;
            font-weight: 700;
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

    api_key = get_runtime_value("TMDB_API_KEY").strip()
    access_token = get_runtime_value("TMDB_BEARER_TOKEN", "TMDB_ACCESS_TOKEN").strip()
    language = st.sidebar.selectbox("TMDB Language", options=language_options, index=language_options.index(default_language))
    return TMDBSettings(api_key=api_key, access_token=access_token, language=language)


def build_youtube_settings() -> YouTubeSettings:
    region_options = ["IN", "PK", "TR", "US", "GB"]
    configured_region = get_runtime_value("YOUTUBE_REGION_CODE", default=DEFAULT_YOUTUBE_REGION)
    default_region = configured_region if configured_region in region_options else "IN"

    api_key = get_runtime_value("YOUTUBE_API_KEY").strip()
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

    st.sidebar.write(f"Watchlist: {len(st.session_state.get('watchlist', []))} saved")
    st.sidebar.caption("Keys stay private. Use local .env, Streamlit secrets, or deployment environment variables.")


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
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.caption(f"{country or 'Drama'} | {year}")
        st.caption("Poster not available in starter mode.")
    return

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
        for index, match in enumerate(local_matches[:4]):
            with st.container(border=True):
                st.markdown(f"**{match['title']}**")
                st.caption(f"{match['country']} | {match['year']} | match {match.get('match_score', 0):.2f}")
                if st.button("Search This Title", key=f"local_match_pick_{index}", use_container_width=True):
                    set_search_context(match["title"], match.get("country", ""))
                    st.rerun()

    if live_matches:
        st.markdown("#### TMDB live matches")
        for index, match in enumerate(live_matches[:4]):
            country = ", ".join(match.get("country_names", [])) or "Unknown"
            year = match.get("year") or "-"
            with st.container(border=True):
                st.markdown(f"**{match['title']}**")
                st.caption(f"{country} | {year}")
                if st.button("Load Live Match", key=f"live_match_pick_{index}", use_container_width=True):
                    set_search_context(match["title"], country if country in SUPPORTED_COUNTRIES else "")
                    st.rerun()
    return

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
    st.caption("Drama discovery workspace")
    st.title(APP_TITLE)
    st.write(APP_SUBTITLE)
    chip_text = " | ".join(
        str(item)
        for item in (
            profile.get("source", "Profile loaded"),
            profile.get("country", "Country unknown"),
            profile.get("status", "Series"),
            profile.get("year", "Year unknown"),
        )
        if item
    )
    st.caption(chip_text)
    return

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

        action_one, action_two = st.columns(2)
        if action_one.button("Save to Watchlist", key=f"save_profile_{profile.get('title', '')}", use_container_width=True):
            add_watchlist_entry(build_watchlist_entry(profile))
            st.rerun()
        if action_two.button("Search This Drama", key=f"search_profile_{profile.get('title', '')}", use_container_width=True):
            set_search_context(profile.get("title", ""), profile.get("country", ""))
            st.rerun()

        if not tmdb_settings.enabled and not profile.get("poster_url"):
            st.warning("Real posters, richer cast, and social handles need TMDB credentials in .env, Streamlit secrets, or deployment environment variables.")


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
                        st.link_button(label, url, use_container_width=True)
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

                action_one, action_two = st.columns(2)
                if action_one.button(
                    "Search This",
                    key=f"search_recommendation_{recommendation.get('title', '')}_{index}",
                    use_container_width=True,
                ):
                    set_search_context(recommendation.get("title", ""), recommendation.get("country", ""))
                    st.rerun()
                if action_two.button(
                    "Save",
                    key=f"save_recommendation_{recommendation.get('title', '')}_{index}",
                    use_container_width=True,
                ):
                    add_watchlist_entry(build_watchlist_entry(recommendation))
                    st.rerun()

                tmdb_link = recommendation.get("tmdb_url") or build_tmdb_search_url(recommendation.get("title", ""))
                youtube_link = build_youtube_search_url(f"{recommendation.get('title', '')} official drama")
                st.link_button("Open TMDB", tmdb_link, use_container_width=True)
                st.link_button("Search YouTube", youtube_link, use_container_width=True)


def render_home_tab(catalog, recommender: DramaRecommender) -> None:
    render_profile_header(
        {
            "source": "Home",
            "country": "India, Pakistan, Turkey",
            "status": MODEL_NAME,
            "year": "2020-2026",
        }
    )

    metric_one, metric_two, metric_three, metric_four = st.columns(4)
    metric_one.metric("Starter titles", int(len(catalog)))
    metric_two.metric("Countries", len(SUPPORTED_COUNTRIES))
    metric_three.metric("Watchlist", len(st.session_state.get("watchlist", [])))
    metric_four.metric("TMDB ready later", "Yes")

    left_column, right_column = st.columns([1.15, 1])

    with left_column:
        with st.container(border=True):
            st.markdown("### Quick Start")
            st.text_input(
                "Type a drama title to move into Search",
                key="home_query",
                placeholder="Try Tere Bin, Parizaad, Heeramandi, Yargi",
            )
            if st.button("Use This Search", key="home_use_query", use_container_width=True):
                set_search_context(st.session_state.get("home_query", ""))
                st.rerun()

            st.caption("Popular starter picks")
            starter_titles = catalog.sort_values(["year", "title"], ascending=[False, True])["title"].tolist()[:6]
            starter_columns = st.columns(3)
            for index, title in enumerate(starter_titles):
                if starter_columns[index % 3].button(title, key=f"home_starter_{index}", use_container_width=True):
                    set_search_context(title)
                    st.rerun()

    with right_column:
        with st.container(border=True):
            st.markdown("### Explore By Country")
            for country in SUPPORTED_COUNTRIES:
                st.markdown(f"**{country}**")
                country_titles = recommender.available_titles(countries=[country], year_range=(2020, 2026))[:3]
                country_columns = st.columns(max(1, min(3, len(country_titles))))
                for index, title in enumerate(country_titles):
                    if country_columns[index % len(country_columns)].button(
                        title,
                        key=f"home_country_{country}_{index}",
                        use_container_width=True,
                    ):
                        set_search_context(title, country)
                        st.rerun()

            if st.button("Surprise Me", key="home_surprise", use_container_width=True):
                random_title = random.choice(catalog["title"].tolist())
                set_search_context(random_title)
                st.rerun()


def render_watchlist_tab() -> None:
    st.markdown("### Watchlist")
    st.caption("Save dramas while browsing, then reopen them here with one click.")

    watchlist = st.session_state.get("watchlist", [])
    if not watchlist:
        st.info("Your watchlist is empty. Save a drama from Search, match results, recommendations, or Catalog.")
        return

    st.metric("Saved dramas", len(watchlist))
    for index, item in enumerate(watchlist):
        with st.container(border=True):
            st.markdown(f"**{item.get('title', 'Saved drama')}**")
            details = [item.get("country", ""), str(item.get("year", "")), item.get("source", "Saved")]
            st.caption(" | ".join([detail for detail in details if detail and detail != "0"]))
            st.write(trim_text(item.get("overview", "No summary stored yet."), limit=180))

            action_one, action_two, action_three = st.columns(3)
            if action_one.button("Search This", key=f"watchlist_search_{index}", use_container_width=True):
                set_search_context(item.get("search_title", item.get("title", "")), item.get("country", ""))
                st.rerun()
            if item.get("tmdb_url"):
                action_two.link_button("Open TMDB", item["tmdb_url"], use_container_width=True)
            if action_three.button("Remove", key=f"watchlist_remove_{index}", use_container_width=True):
                st.session_state["watchlist"].pop(index)
                st.rerun()


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
    if "search_year_range" not in st.session_state:
        st.session_state["search_year_range"] = (max(2020, min_year), max_year)

    filter_column, query_column = st.columns([0.95, 1.25])
    with filter_column:
        selected_countries = st.multiselect(
            "Countries",
            options=list(SUPPORTED_COUNTRIES),
            default=list(SUPPORTED_COUNTRIES),
            key="search_countries",
        )
        year_range = st.slider(
            "Year range",
            min_value=min_year,
            max_value=max_year,
            value=(max(2020, min_year), max_year),
            key="search_year_range",
        )

    with query_column:
        query = st.text_input(
            "Search a drama title",
            placeholder="Try Tere Bin, Ishq Murshid, Yargi, Heeramandi, or your own spelling",
            key="search_query",
        ).strip()
        fallback_titles = recommender.available_titles(countries=selected_countries, year_range=year_range)
        default_fallback = fallback_titles[0] if fallback_titles else catalog.iloc[0]["title"]
        if st.session_state.get("search_fallback_title") not in (fallback_titles or [default_fallback]):
            st.session_state["search_fallback_title"] = default_fallback
        fallback_title = st.selectbox(
            "Starter catalog fallback",
            options=fallback_titles or [default_fallback],
            key="search_fallback_title",
        )

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
    if not filtered.empty:
        preview_title = st.selectbox("Preview a drama from the filtered catalog", options=filtered["title"].tolist(), key="catalog_preview_title")
        preview_row = filtered[filtered["title"] == preview_title].iloc[0].to_dict()
        with st.container(border=True):
            st.markdown(f"**{preview_row['title']}**")
            st.caption(f"{preview_row['country']} | {preview_row['year']} | {preview_row['network']}")
            st.write(trim_text(preview_row.get("overview", "No summary available.")))

            action_one, action_two = st.columns(2)
            if action_one.button("Search This Drama", key="catalog_preview_search", use_container_width=True):
                set_search_context(preview_row["title"], preview_row.get("country", ""))
                st.rerun()
            if action_two.button("Save to Watchlist", key="catalog_preview_save", use_container_width=True):
                add_watchlist_entry(build_watchlist_entry(create_local_profile(preview_row)))
                st.rerun()

    st.dataframe(
        filtered[["title", "country", "year", "language", "status", "network", "genres", "cast"]],
        use_container_width=True,
        hide_index=True,
    )


def render_setup_tab(tmdb_settings: TMDBSettings, youtube_settings: YouTubeSettings) -> None:
    st.markdown("### Setup and source status")
    left_column, right_column = st.columns([1.1, 1])

    with left_column:
        st.info(TMDB_NOTICE)
        st.image(TMDB_LOGO_URL, width=120)

        with st.container(border=True):
            st.markdown("#### Why posters or live links may be missing")
            st.write("The starter catalog ships with text data only. Real posters, richer cast details, TMDB links, and actor biographies need a TMDB token.")
            st.write("You can keep keys private by using local .env, Streamlit secrets, or deployment environment variables.")

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
    catalog = get_catalog(str(DATA_PATH))
    recommender = get_recommender(str(DATA_PATH), str(ARTIFACT_PATH))
    ensure_ui_state(catalog)

    tmdb_settings = build_tmdb_settings()
    youtube_settings = build_youtube_settings()
    render_sidebar_summary(tmdb_settings, youtube_settings)

    home_tab, search_tab, watchlist_tab, catalog_tab, setup_tab = st.tabs(["Home", "Search", "Watchlist", "Catalog", "Setup"])
    with home_tab:
        render_home_tab(catalog, recommender)
    with search_tab:
        render_search_tab(catalog, recommender, tmdb_settings, youtube_settings)
    with watchlist_tab:
        render_watchlist_tab()
    with catalog_tab:
        render_catalog_tab(catalog)
    with setup_tab:
        render_setup_tab(tmdb_settings, youtube_settings)


if __name__ == "__main__":
    main()
