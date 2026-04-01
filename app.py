from __future__ import annotations

import os
from typing import Any

import pandas as pd
import streamlit as st

from src.config import (
    APP_SUBTITLE,
    APP_TITLE,
    DEFAULT_TMDB_LANGUAGE,
    DRAMAS_DATA_PATH,
    MODEL_NAME,
    MOVIES_DATA_PATH,
    TMDB_NOTICE,
)
from src.data import load_combined_catalog
from src.recommender import DramaRecommender
from src.tmdb import TMDBSettings, build_tmdb_search_url, fetch_media_profile, search_titles
from src.youtube import build_youtube_search_url


st.set_page_config(page_title=APP_TITLE, page_icon=":clapper:", layout="wide")


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


def trim_text(value: object, limit: int = 220) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def ensure_ui_state() -> None:
    defaults = {
        "query_input": "",
        "home_query_input": "",
        "search_query_input": "",
        "selected_match_id": None,
        "runtime_tmdb_access": "",
        "runtime_tmdb_key": "",
        "runtime_tmdb_language": DEFAULT_TMDB_LANGUAGE,
        "watchlist": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def queue_query(title: str) -> None:
    clean_title = str(title).strip()
    st.session_state["query_input"] = clean_title
    st.session_state["home_query_input"] = clean_title
    st.session_state["search_query_input"] = clean_title
    st.session_state.pop("selected_match_id", None)


def add_to_watchlist(item: dict[str, Any]) -> bool:
    title = str(item.get("title", "")).strip()
    year = int(item.get("year", 0) or 0)
    content_type = str(item.get("content_type", "Title")).strip() or "Title"
    watch_key = f"{title.lower()}::{year}::{content_type.lower()}"

    watchlist = st.session_state.get("watchlist", [])
    if any(entry.get("watch_key") == watch_key for entry in watchlist):
        return False

    watchlist.append(
        {
            "watch_key": watch_key,
            "title": title,
            "year": year,
            "content_type": content_type,
            "country": str(item.get("country", "")).strip(),
            "overview": str(item.get("overview", "")).strip(),
            "tmdb_url": item.get("tmdb_url") or build_tmdb_search_url(title, media_type="multi"),
            "youtube_url": build_youtube_search_url(f"{title} trailer"),
        }
    )
    st.session_state["watchlist"] = watchlist
    return True


def remove_from_watchlist(watch_key: str) -> None:
    st.session_state["watchlist"] = [
        entry for entry in st.session_state.get("watchlist", []) if entry.get("watch_key") != watch_key
    ]


def build_tmdb_settings() -> TMDBSettings:
    access_token = st.session_state.get("runtime_tmdb_access", "").strip() or get_runtime_value(
        "TMDB_BEARER_TOKEN",
        "TMDB_ACCESS_TOKEN",
    )
    api_key = st.session_state.get("runtime_tmdb_key", "").strip() or get_runtime_value("TMDB_API_KEY")
    language = st.session_state.get("runtime_tmdb_language", DEFAULT_TMDB_LANGUAGE) or DEFAULT_TMDB_LANGUAGE
    return TMDBSettings(api_key=api_key, access_token=access_token, language=language)


@st.cache_data(show_spinner=False)
def get_catalog() -> pd.DataFrame:
    return load_combined_catalog(DRAMAS_DATA_PATH, MOVIES_DATA_PATH)


@st.cache_resource(show_spinner=False)
def get_recommender() -> DramaRecommender:
    return DramaRecommender().fit(get_catalog())


@st.cache_data(show_spinner=False, ttl=3600)
def get_live_matches(query: str, api_key: str, access_token: str, language: str) -> list[dict[str, Any]]:
    settings = TMDBSettings(api_key=api_key, access_token=access_token, language=language)
    return search_titles(query=query, settings=settings, limit=6)


@st.cache_data(show_spinner=False, ttl=3600)
def get_live_profile(
    tmdb_id: int,
    media_type: str,
    api_key: str,
    access_token: str,
    language: str,
) -> dict[str, Any] | None:
    settings = TMDBSettings(api_key=api_key, access_token=access_token, language=language)
    return fetch_media_profile(tmdb_id=tmdb_id, media_type=media_type, settings=settings)


def build_local_profile(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "Starter catalog",
        "content_type": record.get("content_type", "Title"),
        "title": record.get("title", ""),
        "original_title": record.get("title", ""),
        "year": int(record.get("year", 0) or 0),
        "country": record.get("country", ""),
        "language": record.get("language", ""),
        "status": record.get("status", ""),
        "genres": split_tags(record.get("genres", "")),
        "themes": split_tags(record.get("themes", "")),
        "network": record.get("network", ""),
        "overview": record.get("overview", ""),
        "aliases": record.get("aliases", ""),
        "watch_hint": record.get("watch_hint", ""),
        "poster_url": record.get("poster_url", ""),
        "tmdb_url": build_tmdb_search_url(record.get("title", ""), media_type="multi"),
        "social_links": {},
        "cast": [{"name": name} for name in split_tags(record.get("cast", ""))],
        "recommendations": [],
    }


def build_candidates(
    query: str,
    recommender: DramaRecommender,
    tmdb_settings: TMDBSettings,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    local_matches = recommender.search(query, limit=6)
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()

    if tmdb_settings.enabled:
        for match in get_live_matches(query, tmdb_settings.api_key, tmdb_settings.access_token, tmdb_settings.language):
            key = (
                match.get("title", "").lower(),
                int(match.get("year", 0) or 0),
                match.get("content_type", ""),
            )
            if key in seen:
                continue
            seen.add(key)
            match["candidate_id"] = f"live::{match.get('media_type')}::{match.get('tmdb_id')}"
            candidates.append(match)

    for match in local_matches:
        key = (
            match.get("title", "").lower(),
            int(match.get("year", 0) or 0),
            match.get("content_type", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        match["candidate_id"] = f"local::{match.get('title')}::{match.get('year')}::{match.get('content_type')}"
        match["source"] = "Starter catalog"
        candidates.append(match)

    return candidates, local_matches


def render_match_picker(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    option_ids = [candidate["candidate_id"] for candidate in candidates]
    labels = {
        candidate["candidate_id"]: (
            f"{candidate.get('title', 'Unknown')} "
            f"({candidate.get('content_type', 'Title')}, {candidate.get('year', 'Unknown')}) "
            f"- {candidate.get('source', 'Unknown')}"
        )
        for candidate in candidates
    }

    if st.session_state.get("selected_match_id") not in option_ids:
        st.session_state["selected_match_id"] = option_ids[0]

    selected_id = st.selectbox(
        "Choose the best match",
        options=option_ids,
        format_func=lambda option_id: labels[option_id],
        key="selected_match_id",
    )
    return next(candidate for candidate in candidates if candidate["candidate_id"] == selected_id)


def resolve_profile(
    selected_candidate: dict[str, Any],
    local_matches: list[dict[str, Any]],
    tmdb_settings: TMDBSettings,
    recommender: DramaRecommender,
) -> tuple[dict[str, Any], str | None]:
    if selected_candidate["candidate_id"].startswith("live::") and tmdb_settings.enabled:
        profile = get_live_profile(
            int(selected_candidate["tmdb_id"]),
            selected_candidate["media_type"],
            tmdb_settings.api_key,
            tmdb_settings.access_token,
            tmdb_settings.language,
        )
        if profile:
            anchor_title = local_matches[0]["title"] if local_matches else None
            return profile, anchor_title

    local_record = recommender.get_drama(selected_candidate["title"])
    return build_local_profile(local_record), local_record["title"]


def render_top_metrics(catalog: pd.DataFrame, tmdb_settings: TMDBSettings) -> None:
    serial_count = int(catalog["content_type"].eq("Serial").sum())
    movie_count = int(catalog["content_type"].eq("Movie").sum())
    country_count = int(catalog["country"].replace("", pd.NA).dropna().nunique())

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Titles", len(catalog))
    col2.metric("Serials", serial_count)
    col3.metric("Movies", movie_count)
    col4.metric("Countries", country_count)

    if tmdb_settings.enabled:
        st.success("TMDb live search is enabled.")
    else:
        st.info("TMDb live search is optional. The starter catalog still works without it.")


def render_quick_picks(catalog: pd.DataFrame) -> None:
    preferred_titles = ["Ishq Murshid", "Tere Bin", "Yargi", "RRR", "Pushpa", "Heeramandi"]
    catalog_titles = catalog["title"].tolist()
    examples = [title for title in preferred_titles if title in catalog_titles]
    if len(examples) < 6:
        for title in catalog_titles:
            if title not in examples:
                examples.append(title)
            if len(examples) == 6:
                break

    st.write("Quick picks")
    columns = st.columns(3)
    for index, title in enumerate(examples):
        if columns[index % 3].button(title, key=f"quick_pick_{index}", use_container_width=True):
            queue_query(title)
            st.rerun()


def render_poster(profile: dict[str, Any]) -> None:
    with st.container(border=True):
        if profile.get("poster_url"):
            st.image(profile["poster_url"], use_container_width=True)
        else:
            st.write("Poster not available.")
            st.caption(
                f"{profile.get('content_type', 'Title')} | "
                f"{profile.get('country', 'Unknown')} | "
                f"{profile.get('year', 'Unknown')}"
            )


def render_profile(profile: dict[str, Any]) -> None:
    left, right = st.columns([1, 2])

    with left:
        render_poster(profile)

        save_key = f"save_profile_{profile.get('title', '')}_{profile.get('year', 0)}"
        if st.button("Save to watchlist", key=save_key, use_container_width=True):
            if add_to_watchlist(profile):
                st.success("Saved to watchlist.")
            else:
                st.info("Already saved.")

        st.link_button(
            "Open TMDb",
            profile.get("tmdb_url") or build_tmdb_search_url(profile.get("title", ""), media_type="multi"),
            use_container_width=True,
        )
        st.link_button(
            "Search YouTube",
            build_youtube_search_url(f"{profile.get('title', '')} trailer"),
            use_container_width=True,
        )

    with right:
        title = profile.get("title", "Unknown title")
        year = profile.get("year", "Unknown")
        st.subheader(f"{title} ({year})")

        detail_parts = [
            profile.get("content_type", ""),
            profile.get("country", ""),
            profile.get("language", ""),
            profile.get("status", ""),
            profile.get("source", ""),
        ]
        detail_parts = [part for part in detail_parts if part and part != "0"]
        if detail_parts:
            st.caption(" | ".join(detail_parts))

        st.write(profile.get("overview") or "No summary available yet.")

        genres = profile.get("genres") or []
        if genres:
            st.write(f"Genres: {', '.join(genres)}")

        themes = profile.get("themes") or []
        if themes:
            st.write(f"Themes: {', '.join(themes)}")

        network = profile.get("network", "")
        if network:
            st.write(f"Network / Studio: {network}")

        cast_entries = profile.get("cast") or []
        cast_names = [member.get("name", "") for member in cast_entries if member.get("name")]
        if cast_names:
            st.write(f"Cast: {', '.join(cast_names[:10])}")

        if profile.get("aliases"):
            st.write(f"Also known as: {profile.get('aliases')}")

        if profile.get("watch_hint"):
            st.info(profile["watch_hint"])

        social_links = profile.get("social_links") or {}
        if social_links:
            st.write("Links")
            link_columns = st.columns(min(4, len(social_links)))
            for index, (label, url) in enumerate(social_links.items()):
                link_columns[index % len(link_columns)].link_button(
                    label,
                    url,
                    key=f"profile_link_{label}_{index}",
                    use_container_width=True,
                )


def render_recommendations(
    profile: dict[str, Any],
    recommender: DramaRecommender,
    anchor_title: str | None,
) -> None:
    live_recommendations = profile.get("recommendations") or []
    if live_recommendations:
        recommendations = live_recommendations[:6]
    elif anchor_title:
        try:
            recommendations = recommender.recommend(anchor_title, top_n=6)
        except Exception:
            recommendations = []
    else:
        recommendations = []

    st.subheader("Recommendations")
    if not recommendations:
        st.info("No recommendations are available for this match yet.")
        return

    columns = st.columns(3)
    for index, recommendation in enumerate(recommendations):
        with columns[index % 3]:
            with st.container(border=True):
                if recommendation.get("poster_url"):
                    st.image(recommendation["poster_url"], use_container_width=True)

                st.markdown(f"**{recommendation.get('title', 'Unknown title')}**")
                caption_parts = [
                    recommendation.get("content_type", ""),
                    str(recommendation.get("year", "")),
                    recommendation.get("country", ""),
                ]
                caption_parts = [part for part in caption_parts if part and part != "0"]
                if recommendation.get("similarity") is not None:
                    caption_parts.append(f"match {recommendation['similarity']:.0%}")
                if caption_parts:
                    st.caption(" | ".join(caption_parts))

                st.write(trim_text(recommendation.get("overview", "No summary available."), 160))

                button_left, button_right = st.columns(2)
                if button_left.button(
                    "Use this title",
                    key=f"rec_use_{index}_{recommendation.get('title', '')}",
                    use_container_width=True,
                ):
                    queue_query(recommendation.get("title", ""))
                    st.rerun()

                if button_right.button(
                    "Save",
                    key=f"rec_save_{index}_{recommendation.get('title', '')}",
                    use_container_width=True,
                ):
                    if add_to_watchlist(recommendation):
                        st.success("Saved.")
                    else:
                        st.info("Already saved.")

                st.link_button(
                    "Open TMDb",
                    recommendation.get("tmdb_url")
                    or build_tmdb_search_url(recommendation.get("title", ""), media_type="multi"),
                    key=f"rec_tmdb_{index}_{recommendation.get('title', '')}",
                    use_container_width=True,
                )


def render_search_results(query: str, recommender: DramaRecommender, tmdb_settings: TMDBSettings) -> None:
    candidates, local_matches = build_candidates(query, recommender, tmdb_settings)
    if not candidates:
        st.error("No match found. Try another spelling or a different title.")
        return

    selected_candidate = render_match_picker(candidates)
    profile, anchor_title = resolve_profile(selected_candidate, local_matches, tmdb_settings, recommender)
    render_profile(profile)
    render_recommendations(profile, recommender, anchor_title)
    st.caption(TMDB_NOTICE)


def render_home_tab(catalog: pd.DataFrame, tmdb_settings: TMDBSettings) -> None:
    st.title(APP_TITLE)
    st.write(APP_SUBTITLE)
    render_top_metrics(catalog, tmdb_settings)

    st.divider()
    st.subheader("Start here")
    with st.form("home_search_form", clear_on_submit=False):
        st.text_input(
            "Search for a movie or serial",
            key="home_query_input",
            placeholder="Try Ishq Murshid, Tere Bin, Yargi, Pushpa, or RRR",
        )
        submitted = st.form_submit_button("Search now", use_container_width=True)

    if submitted:
        queue_query(st.session_state.get("home_query_input", ""))
        st.rerun()

    if st.session_state.get("query_input"):
        st.success(f"Current search loaded: {st.session_state['query_input']}")

    render_quick_picks(catalog)

    st.divider()
    st.subheader("How it works")
    st.write("1. Search for a title.")
    st.write("2. Pick the closest match in the Search tab.")
    st.write("3. Save titles you like and explore similar recommendations.")

    preview = catalog[["title", "content_type", "country", "year", "genres"]].head(10).copy()
    st.subheader("Catalog preview")
    st.dataframe(preview, use_container_width=True, hide_index=True)


def render_search_tab(recommender: DramaRecommender, tmdb_settings: TMDBSettings) -> None:
    st.header("Search")

    with st.form("search_form", clear_on_submit=False):
        st.text_input(
            "Title search",
            key="search_query_input",
            placeholder="Search for a movie or serial title",
        )
        submitted = st.form_submit_button("Find matches", use_container_width=True)

    if submitted:
        queue_query(st.session_state.get("search_query_input", ""))
        st.rerun()

    query = st.session_state.get("query_input", "").strip()
    if not query:
        st.info("Enter a title above or use a quick pick from the Home tab.")
        return

    st.caption(f"Showing results for: {query}")
    render_search_results(query, recommender, tmdb_settings)


def render_catalog_tab(catalog: pd.DataFrame) -> None:
    st.header("Catalog")

    country_options = sorted(country for country in catalog["country"].dropna().unique() if str(country).strip())
    type_options = sorted(content_type for content_type in catalog["content_type"].dropna().unique() if str(content_type).strip())
    year_min = int(catalog["year"].min())
    year_max = int(catalog["year"].max())

    col1, col2 = st.columns(2)
    text_query = col1.text_input(
        "Filter by title, genre, theme, or country",
        key="catalog_text_query",
        placeholder="Search the local catalog",
    ).strip()
    selected_types = col2.multiselect("Type", options=type_options, key="catalog_types")

    col3, col4 = st.columns(2)
    selected_countries = col3.multiselect("Country", options=country_options, key="catalog_countries")
    selected_years = col4.slider(
        "Year range",
        min_value=year_min,
        max_value=year_max,
        value=(year_min, year_max),
        key="catalog_years",
    )

    filtered = catalog.copy()
    if selected_types:
        filtered = filtered[filtered["content_type"].isin(selected_types)]
    if selected_countries:
        filtered = filtered[filtered["country"].isin(selected_countries)]
    if selected_years:
        filtered = filtered[(filtered["year"] >= selected_years[0]) & (filtered["year"] <= selected_years[1])]
    if text_query:
        search_blob = (
            filtered["title"].fillna("")
            + " "
            + filtered["genres"].fillna("")
            + " "
            + filtered["themes"].fillna("")
            + " "
            + filtered["country"].fillna("")
            + " "
            + filtered["overview"].fillna("")
        )
        filtered = filtered[search_blob.str.contains(text_query, case=False, na=False)]

    st.caption(f"{len(filtered)} titles in the current filter")
    st.dataframe(
        filtered[["title", "content_type", "country", "year", "genres"]],
        use_container_width=True,
        hide_index=True,
        height=320,
    )

    if filtered.empty:
        st.warning("No titles match the current filter.")
        return

    options = [
        f"{row.title} ({row.content_type}, {row.year})"
        for row in filtered[["title", "content_type", "year"]].itertuples(index=False)
    ]
    selected_label = st.selectbox("Inspect a title", options=options, key="catalog_selection")
    selected_title = selected_label.rsplit(" (", 1)[0]
    selected_row = filtered.loc[filtered["title"] == selected_title].iloc[0].to_dict()

    st.write(trim_text(selected_row.get("overview", "No summary available yet."), 320))
    action_left, action_mid, action_right = st.columns(3)
    if action_left.button("Search this title", key="catalog_search_button", use_container_width=True):
        queue_query(selected_row.get("title", ""))
        st.rerun()
    if action_mid.button("Save to watchlist", key="catalog_save_button", use_container_width=True):
        if add_to_watchlist(selected_row):
            st.success("Saved to watchlist.")
        else:
            st.info("Already saved.")
    action_right.link_button(
        "Open TMDb",
        build_tmdb_search_url(selected_row.get("title", ""), media_type="multi"),
        use_container_width=True,
    )


def render_watchlist_tab() -> None:
    st.header("Watchlist")
    watchlist = st.session_state.get("watchlist", [])

    if not watchlist:
        st.info("Your watchlist is empty. Save titles from Search or Catalog.")
        return

    top_left, top_right = st.columns([1, 1])
    top_left.metric("Saved titles", len(watchlist))
    if top_right.button("Clear watchlist", key="clear_watchlist", use_container_width=True):
        st.session_state["watchlist"] = []
        st.rerun()

    for entry in watchlist:
        with st.container(border=True):
            st.markdown(f"**{entry.get('title', 'Unknown title')}**")
            caption_parts = [
                entry.get("content_type", ""),
                str(entry.get("year", "")),
                entry.get("country", ""),
            ]
            caption_parts = [part for part in caption_parts if part and part != "0"]
            if caption_parts:
                st.caption(" | ".join(caption_parts))

            if entry.get("overview"):
                st.write(trim_text(entry["overview"], 180))

            col1, col2, col3, col4 = st.columns(4)
            if col1.button(
                "Search",
                key=f"watch_search_{entry.get('watch_key')}",
                use_container_width=True,
            ):
                queue_query(entry.get("title", ""))
                st.rerun()
            col2.link_button(
                "TMDb",
                entry.get("tmdb_url") or build_tmdb_search_url(entry.get("title", ""), media_type="multi"),
                key=f"watch_tmdb_{entry.get('watch_key')}",
                use_container_width=True,
            )
            col3.link_button(
                "YouTube",
                entry.get("youtube_url") or build_youtube_search_url(f"{entry.get('title', '')} trailer"),
                key=f"watch_youtube_{entry.get('watch_key')}",
                use_container_width=True,
            )
            if col4.button(
                "Remove",
                key=f"watch_remove_{entry.get('watch_key')}",
                use_container_width=True,
            ):
                remove_from_watchlist(entry.get("watch_key", ""))
                st.rerun()


def render_setup_tab(catalog: pd.DataFrame, tmdb_settings: TMDBSettings) -> None:
    st.header("Setup")
    st.write("TMDb is optional. Leave these fields empty if you only want the local starter catalog.")

    st.text_input(
        "TMDb bearer token",
        type="password",
        key="runtime_tmdb_access",
        help="This stays in the current Streamlit session unless you already set it in secrets or environment variables.",
    )
    st.text_input(
        "TMDb API key",
        type="password",
        key="runtime_tmdb_key",
        help="Optional alternative to the bearer token.",
    )

    language_options = ["en-US", "hi-IN"]
    if DEFAULT_TMDB_LANGUAGE not in language_options:
        language_options.insert(0, DEFAULT_TMDB_LANGUAGE)
    st.selectbox("TMDb language", options=language_options, key="runtime_tmdb_language")

    status_left, status_right = st.columns(2)
    if tmdb_settings.enabled:
        status_left.success("TMDb live search is ready.")
    else:
        status_left.info("TMDb live search is off. Local search still works.")
    status_right.info(f"Starter catalog size: {len(catalog)} titles")

    st.caption(TMDB_NOTICE)
    st.caption(f"Model: {MODEL_NAME}")


def main() -> None:
    ensure_ui_state()

    catalog = get_catalog()
    recommender = get_recommender()
    tmdb_settings = build_tmdb_settings()

    home_tab, search_tab, catalog_tab, watchlist_tab, setup_tab = st.tabs(
        ["Home", "Search", "Catalog", "Watchlist", "Setup"]
    )

    with home_tab:
        render_home_tab(catalog, tmdb_settings)

    with search_tab:
        render_search_tab(recommender, tmdb_settings)

    with catalog_tab:
        render_catalog_tab(catalog)

    with watchlist_tab:
        render_watchlist_tab()

    with setup_tab:
        render_setup_tab(catalog, tmdb_settings)


if __name__ == "__main__":
    main()
