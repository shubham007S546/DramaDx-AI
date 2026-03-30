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
    TMDB_FAQ_URL,
    TMDB_LOGO_GUIDE_URL,
    TMDB_LOGO_URL,
    TMDB_NOTICE,
    TMDB_SITE_URL,
    YOUTUBE_API_DOCS_URL,
    YOUTUBE_SITE_URL,
)
from src.data import load_movies
from src.recommender import MovieRecommender
from src.tmdb import TMDBSettings, fetch_movie_metadata
from src.youtube import YouTubeSettings, fetch_trailer


st.set_page_config(page_title=APP_TITLE, page_icon="🎬", layout="wide")


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


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(1, 180, 228, 0.16), transparent 26%),
                radial-gradient(circle at top right, rgba(13, 37, 63, 0.10), transparent 20%),
                linear-gradient(180deg, #f4f8fb 0%, #ffffff 55%, #f8fbfd 100%);
        }
        .block-container {
            padding-top: 1.4rem;
            padding-bottom: 2.8rem;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.5rem;
            margin-bottom: 0.9rem;
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 999px;
            padding: 0.6rem 1rem;
            background: rgba(13, 37, 63, 0.05);
        }
        .hero-panel {
            padding: 1.7rem 1.8rem;
            border-radius: 28px;
            background: linear-gradient(135deg, #081f34 0%, #0d253f 48%, #01b4e4 100%);
            color: #ffffff;
            box-shadow: 0 24px 50px rgba(13, 37, 63, 0.16);
        }
        .hero-title {
            margin: 0;
            font-size: 2.6rem;
            line-height: 1.05;
        }
        .hero-copy {
            margin-top: 0.8rem;
            margin-bottom: 1rem;
            font-size: 1rem;
            line-height: 1.7;
            max-width: 780px;
        }
        .chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-top: 0.8rem;
        }
        .chip {
            display: inline-flex;
            align-items: center;
            padding: 0.35rem 0.75rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.14);
            border: 1px solid rgba(255, 255, 255, 0.18);
            font-size: 0.88rem;
        }
        .soft-card {
            background: rgba(255, 255, 255, 0.82);
            border: 1px solid rgba(13, 37, 63, 0.08);
            border-radius: 24px;
            padding: 1.1rem 1.2rem;
            box-shadow: 0 14px 30px rgba(13, 37, 63, 0.06);
        }
        .section-note {
            color: #425466;
            font-size: 0.95rem;
            line-height: 1.6;
        }
        .tmdb-note {
            border: 1px solid rgba(1, 180, 228, 0.22);
            border-radius: 20px;
            padding: 1rem 1.1rem;
            background: rgba(1, 180, 228, 0.07);
        }
        .tmdb-note p {
            margin: 0.2rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def split_tags(value: object) -> list[str]:
    return [part.strip() for part in str(value).split(",") if part and part.strip()]


@st.cache_data(show_spinner=False)
def get_catalog(dataset_path: str):
    return load_movies(Path(dataset_path))


@st.cache_resource(show_spinner=False)
def get_recommender(dataset_path: str, artifact_path: str) -> MovieRecommender:
    dataset = Path(dataset_path)
    artifact = Path(artifact_path)

    if artifact.exists() and artifact.stat().st_mtime >= dataset.stat().st_mtime:
        try:
            return MovieRecommender.load(artifact)
        except Exception:
            pass

    recommender = MovieRecommender().fit(load_movies(dataset))
    try:
        recommender.save(artifact)
    except Exception:
        pass
    return recommender


def build_tmdb_settings() -> TMDBSettings:
    st.sidebar.header("TMDB Settings")
    language_options = ["en-US", "hi-IN"]
    configured_language = get_runtime_value("TMDB_LANGUAGE", default=DEFAULT_TMDB_LANGUAGE)
    default_language = configured_language if configured_language in language_options else "en-US"

    api_key = get_runtime_value("TMDB_API_KEY").strip()
    access_token = get_runtime_value("TMDB_ACCESS_TOKEN", "TMDB_BEARER_TOKEN").strip()
    language = st.sidebar.selectbox(
        "TMDB Language",
        options=language_options,
        index=language_options.index(default_language),
    )
    st.sidebar.caption(
        "Credentials are loaded privately from secrets or environment variables. They are not shown in the UI."
    )
    return TMDBSettings(api_key=api_key, access_token=access_token, language=language)


def build_youtube_settings() -> YouTubeSettings:
    st.sidebar.header("YouTube Trailer Settings")
    region_options = ["IN", "US", "GB", "CA", "AU"]
    configured_region = get_runtime_value("YOUTUBE_REGION_CODE", default=DEFAULT_YOUTUBE_REGION)
    default_region = configured_region if configured_region in region_options else "IN"

    api_key = get_runtime_value("YOUTUBE_API_KEY").strip()
    region_code = st.sidebar.selectbox(
        "YouTube Region",
        options=region_options,
        index=region_options.index(default_region),
    )
    st.sidebar.caption("Trailer search is optional and uses hidden credentials from secrets or environment variables.")
    return YouTubeSettings(api_key=api_key, region_code=region_code)


def render_sidebar_summary(tmdb_settings: TMDBSettings, youtube_settings: YouTubeSettings) -> None:
    st.sidebar.divider()
    st.sidebar.markdown("### Project Status")
    if tmdb_settings.enabled:
        st.sidebar.success("TMDB live enrichment is ready.")
    else:
        st.sidebar.info("TMDB is optional. Add a key for posters, ratings, and movie links.")

    if youtube_settings.enabled:
        st.sidebar.success("YouTube trailer search is ready.")
    else:
        st.sidebar.info("YouTube is optional. Add a key for trailer buttons and embeds.")

    st.sidebar.caption("Keys stay private. Configure them in deployment secrets, `.streamlit/secrets.toml`, or environment variables.")


@st.cache_data(show_spinner=False, ttl=86400)
def get_tmdb_payload(
    title: str,
    year: int,
    api_key: str,
    access_token: str,
    language: str,
):
    if not api_key and not access_token:
        return None

    return fetch_movie_metadata(
        title=title,
        settings=TMDBSettings(api_key=api_key, access_token=access_token, language=language),
        year=year,
    )


@st.cache_data(show_spinner=False, ttl=86400)
def get_trailer_payload(title: str, year: int, api_key: str, region_code: str):
    if not api_key:
        return None

    return fetch_trailer(
        title=title,
        settings=YouTubeSettings(api_key=api_key, region_code=region_code),
        year=year,
    )


def ensure_ui_state(titles: list[str], tmdb_enabled: bool, youtube_enabled: bool) -> None:
    default_title = "Inception" if "Inception" in titles else titles[0]

    if "selected_title" not in st.session_state or st.session_state["selected_title"] not in titles:
        st.session_state["selected_title"] = default_title
    if "top_n" not in st.session_state:
        st.session_state["top_n"] = 6
    if "enrich_with_tmdb" not in st.session_state:
        st.session_state["enrich_with_tmdb"] = False
    if "show_youtube_trailers" not in st.session_state:
        st.session_state["show_youtube_trailers"] = False


def compute_catalog_stats(catalog) -> dict[str, int]:
    genre_count = len(
        {
            genre
            for value in catalog["genres"].tolist()
            for genre in split_tags(value)
        }
    )
    director_count = len({value for value in catalog["director"].tolist() if str(value).strip()})
    return {
        "total_movies": int(len(catalog)),
        "genre_count": genre_count,
        "director_count": director_count,
        "start_year": int(catalog["year"].min()),
        "end_year": int(catalog["year"].max()),
    }


def get_spotlight_movies(catalog, limit: int = 6) -> list[dict]:
    preferred_titles = [
        "Interstellar",
        "Inception",
        "Dune",
        "Parasite",
        "The Matrix",
        "The Dark Knight",
    ]
    spotlight: list[dict] = []
    seen_titles: set[str] = set()

    for title in preferred_titles:
        matches = catalog[catalog["title"] == title]
        if not matches.empty:
            record = matches.iloc[0].to_dict()
            spotlight.append(record)
            seen_titles.add(record["title"])

    if len(spotlight) < limit:
        for _, row in catalog.sort_values(["year", "title"], ascending=[False, True]).iterrows():
            if row["title"] in seen_titles:
                continue
            spotlight.append(row.to_dict())
            seen_titles.add(row["title"])
            if len(spotlight) >= limit:
                break

    return spotlight[:limit]


def render_home_tab(catalog, tmdb_settings: TMDBSettings, youtube_settings: YouTubeSettings) -> None:
    stats = compute_catalog_stats(catalog)
    spotlight = get_spotlight_movies(catalog)
    tmdb_label = "Connected" if tmdb_settings.enabled else "Optional"
    youtube_label = "Connected" if youtube_settings.enabled else "Optional"

    st.markdown(
        f"""
        <div class="hero-panel">
          <p style="margin: 0; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.78;">Movie Discovery Workspace</p>
          <h1 class="hero-title">{APP_TITLE}</h1>
          <p class="hero-copy">{APP_SUBTITLE}. Start on this home screen, then jump into Discover for instant recommendations powered by the local model, with TMDB and YouTube ready whenever keys are available.</p>
          <div class="chip-row">
            <span class="chip">Catalog-ready from day one</span>
            <span class="chip">TMDB: {tmdb_label}</span>
            <span class="chip">YouTube: {youtube_label}</span>
            <span class="chip">{MODEL_NAME}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    metric_one, metric_two, metric_three, metric_four = st.columns(4)
    metric_one.metric("Movies In Catalog", stats["total_movies"])
    metric_two.metric("Genres Covered", stats["genre_count"])
    metric_three.metric("Directors Featured", stats["director_count"])
    metric_four.metric("Catalog Range", f"{stats['start_year']} - {stats['end_year']}")

    left_column, right_column = st.columns([1.3, 1])

    with left_column:
        st.markdown("### Quick Start")
        step_one, step_two, step_three = st.columns(3)
        with step_one:
            with st.container(border=True):
                st.markdown("**1. Open Discover**")
                st.write("Choose a movie you already like and let the local recommender find similar titles instantly.")
        with step_two:
            with st.container(border=True):
                st.markdown("**2. Turn on live enrichment**")
                st.write("If private credentials are configured for the app, you can turn on live TMDB and YouTube enrichment here.")
        with step_three:
            with st.container(border=True):
                st.markdown("**3. Browse and compare**")
                st.write("Use the Catalog tab to search, filter by genre, and explore the starter dataset.")

        st.markdown("### Spotlight Picks")
        spotlight_columns = st.columns(3)
        for index, movie in enumerate(spotlight):
            with spotlight_columns[index % 3]:
                with st.container(border=True):
                    st.caption(f"{movie['year']} • {movie['genres']}")
                    st.markdown(f"**{movie['title']}**")
                    st.write(movie["overview"])
                    if st.button(f"Use {movie['title']}", key=f"home_pick_{index}", use_container_width=True):
                        st.session_state["selected_title"] = movie["title"]
                        st.success("Movie loaded. Open the Discover tab to see recommendations.")

    with right_column:
        with st.container(border=True):
            st.markdown("### Current Setup")
            st.write("The project is ready in offline mode right now, and the live APIs stay optional.")
            st.metric("TMDB Live Mode", "Ready" if tmdb_settings.enabled else "Waiting For Key")
            st.metric("YouTube Trailers", "Ready" if youtube_settings.enabled else "Waiting For Key")
            st.caption("Credentials are kept outside the visible UI and loaded privately at runtime.")

        with st.container(border=True):
            st.markdown("### What You Unlock")
            st.write("**Without any API keys**")
            st.write("Local recommendations, starter catalog browsing, and a complete Streamlit experience.")
            st.write("**With TMDB**")
            st.write("Movie posters, live ratings, fresher overviews, and direct TMDB links.")
            st.write("**With YouTube**")
            st.write("Trailer embeds for the selected movie plus trailer buttons in recommendation cards.")


def render_selected_movie(
    movie: dict,
    tmdb_payload: dict | None,
    youtube_settings: YouTubeSettings,
    show_trailer: bool,
) -> None:
    image_column, content_column = st.columns([0.9, 1.6])

    with image_column:
        if tmdb_payload and tmdb_payload.get("poster_url"):
            st.image(tmdb_payload["poster_url"], use_container_width=True)
        else:
            with st.container(border=True):
                st.markdown("#### Poster Preview")
                st.caption("Live TMDB artwork is unavailable right now, so the app is showing the local catalog view.")

    with content_column:
        with st.container(border=True):
            st.subheader(f"{movie['title']} ({movie['year']})")
            st.caption(movie["genres"])
            st.write(movie["overview"])

            if movie.get("director"):
                st.write(f"**Director:** {movie['director']}")

            if tmdb_payload and tmdb_payload.get("release_date"):
                st.write(f"**Release date:** {tmdb_payload['release_date']}")

            if tmdb_payload and tmdb_payload.get("vote_average") is not None:
                st.write(
                    f"**TMDB rating:** {tmdb_payload['vote_average']}/10 from {tmdb_payload.get('vote_count', 0)} votes"
                )

            if tmdb_payload and tmdb_payload.get("tmdb_url"):
                st.link_button("Open on TMDB", tmdb_payload["tmdb_url"], use_container_width=True)

    if show_trailer and youtube_settings.enabled:
        trailer = get_trailer_payload(
            title=movie["title"],
            year=movie["year"],
            api_key=youtube_settings.api_key,
            region_code=youtube_settings.region_code,
        )
        with st.container(border=True):
            st.markdown("### Trailer")
            if trailer and trailer.get("watch_url"):
                st.video(trailer["watch_url"])
                st.caption(f"{trailer.get('title', 'Trailer')} • {trailer.get('channel_title', 'YouTube')}")
            else:
                st.caption("No trailer result came back from YouTube for this title yet.")


def render_recommendation_cards(
    recommendations: list[dict],
    tmdb_settings: TMDBSettings,
    enrich_with_tmdb: bool,
    youtube_settings: YouTubeSettings,
    show_trailers: bool,
) -> None:
    columns = st.columns(3)
    for index, recommendation in enumerate(recommendations):
        tmdb_payload = None
        if enrich_with_tmdb and tmdb_settings.enabled:
            tmdb_payload = get_tmdb_payload(
                title=recommendation["title"],
                year=recommendation["year"],
                api_key=tmdb_settings.api_key,
                access_token=tmdb_settings.access_token,
                language=tmdb_settings.language,
            )

        with columns[index % 3]:
            with st.container(border=True):
                if tmdb_payload and tmdb_payload.get("poster_url"):
                    st.image(tmdb_payload["poster_url"], use_container_width=True)

                st.subheader(f"{recommendation['title']} ({recommendation['year']})")
                st.caption(recommendation["genres"])
                st.progress(recommendation["similarity"], text=f"Match score {recommendation['similarity']:.0%}")

                overview = recommendation["overview"]
                if tmdb_payload and tmdb_payload.get("overview"):
                    overview = tmdb_payload["overview"]
                st.write(overview)

                if recommendation.get("director"):
                    st.caption(f"Director: {recommendation['director']}")

                if tmdb_payload and tmdb_payload.get("vote_average") is not None:
                    st.caption(
                        f"TMDB rating: {tmdb_payload['vote_average']}/10 from {tmdb_payload.get('vote_count', 0)} votes"
                    )

                if tmdb_payload and tmdb_payload.get("tmdb_url"):
                    st.link_button(
                        "Open on TMDB",
                        tmdb_payload["tmdb_url"],
                        key=f"tmdb_link_{recommendation['title']}_{recommendation['year']}",
                        use_container_width=True,
                    )

                if show_trailers and youtube_settings.enabled:
                    trailer = get_trailer_payload(
                        title=recommendation["title"],
                        year=recommendation["year"],
                        api_key=youtube_settings.api_key,
                        region_code=youtube_settings.region_code,
                    )
                    if trailer and trailer.get("watch_url"):
                        st.link_button(
                            "Watch Trailer",
                            trailer["watch_url"],
                            key=f"trailer_link_{recommendation['title']}_{recommendation['year']}",
                            use_container_width=True,
                        )


def render_discover_tab(
    recommender: MovieRecommender,
    tmdb_settings: TMDBSettings,
    youtube_settings: YouTubeSettings,
) -> None:
    titles = recommender.available_titles()
    ensure_ui_state(titles, tmdb_settings.enabled, youtube_settings.enabled)

    st.markdown("### Discover Recommendations")
    st.caption("Pick one film, then explore similar titles with optional posters, ratings, and trailers.")

    controls_column, detail_column = st.columns([1, 1.6])

    with controls_column:
        with st.container(border=True):
            st.selectbox("Choose a movie you like", options=titles, key="selected_title")
            st.slider("Number of recommendations", min_value=3, max_value=10, key="top_n")
            st.toggle(
                "Use TMDB live enrichment",
                key="enrich_with_tmdb",
                disabled=not tmdb_settings.enabled,
                help="Enable posters, ratings, and fresher descriptions when TMDB credentials are available.",
            )
            st.toggle(
                "Use YouTube trailer enrichment",
                key="show_youtube_trailers",
                disabled=not youtube_settings.enabled,
                help="Enable trailer embeds and trailer buttons when a YouTube key is available.",
            )

            action_one, action_two = st.columns(2)
            with action_one:
                if st.button("Surprise Me", use_container_width=True):
                    st.session_state["selected_title"] = random.choice(titles)
                    st.rerun()
            with action_two:
                if st.button("Refresh Picks", type="primary", use_container_width=True):
                    st.rerun()

            if not tmdb_settings.enabled:
                st.info("TMDB is optional. Add a key in the sidebar when you want live posters and ratings.")
            if not youtube_settings.enabled:
                st.info("YouTube is optional. Add a key in the sidebar when you want trailer embeds.")

    selected_movie = recommender.get_movie(st.session_state["selected_title"])
    recommendations = recommender.recommend(
        st.session_state["selected_title"],
        top_n=st.session_state["top_n"],
    )

    selected_tmdb_payload = None
    if st.session_state["enrich_with_tmdb"] and tmdb_settings.enabled:
        selected_tmdb_payload = get_tmdb_payload(
            title=selected_movie["title"],
            year=int(selected_movie["year"]),
            api_key=tmdb_settings.api_key,
            access_token=tmdb_settings.access_token,
            language=tmdb_settings.language,
        )

    with detail_column:
        render_selected_movie(
            selected_movie,
            tmdb_payload=selected_tmdb_payload,
            youtube_settings=youtube_settings,
            show_trailer=st.session_state["show_youtube_trailers"],
        )

    st.markdown("### Recommended For You")
    render_recommendation_cards(
        recommendations,
        tmdb_settings=tmdb_settings,
        enrich_with_tmdb=st.session_state["enrich_with_tmdb"],
        youtube_settings=youtube_settings,
        show_trailers=st.session_state["show_youtube_trailers"],
    )


def render_catalog_tab(catalog) -> None:
    st.markdown("### Browse The Starter Catalog")
    st.caption("Search across titles, genres, directors, and keywords, then narrow the list by genre or decade.")

    searchable_columns = ["title", "genres", "keywords", "director", "overview"]
    search_query = st.text_input(
        "Search the catalog",
        placeholder="Try sci-fi, Nolan, dream, or survival",
    ).strip()

    all_genres = sorted({genre for value in catalog["genres"].tolist() for genre in split_tags(value)})
    selected_genres = st.multiselect("Filter by genre", options=all_genres)

    catalog_with_decade = catalog.assign(decade=(catalog["year"] // 10) * 10)
    decade_options = [f"{decade}s" for decade in sorted(catalog_with_decade["decade"].unique())]
    selected_decade = st.selectbox("Filter by decade", options=["All"] + decade_options)
    sort_option = st.selectbox(
        "Sort catalog by",
        options=["Title (A-Z)", "Newest first", "Oldest first"],
    )

    filtered_catalog = catalog.copy()

    if search_query:
        search_text = filtered_catalog[searchable_columns].fillna("").agg(" ".join, axis=1)
        filtered_catalog = filtered_catalog[search_text.str.contains(search_query, case=False, na=False)]

    if selected_genres:
        selected_set = {genre.lower() for genre in selected_genres}
        filtered_catalog = filtered_catalog[
            filtered_catalog["genres"].map(
                lambda value: bool(selected_set.intersection({genre.lower() for genre in split_tags(value)}))
            )
        ]

    if selected_decade != "All":
        chosen_decade = int(selected_decade[:-1])
        filtered_catalog = filtered_catalog[(filtered_catalog["year"] >= chosen_decade) & (filtered_catalog["year"] < chosen_decade + 10)]

    if sort_option == "Newest first":
        filtered_catalog = filtered_catalog.sort_values(["year", "title"], ascending=[False, True])
    elif sort_option == "Oldest first":
        filtered_catalog = filtered_catalog.sort_values(["year", "title"], ascending=[True, True])
    else:
        filtered_catalog = filtered_catalog.sort_values("title")

    summary_one, summary_two = st.columns(2)
    summary_one.metric("Visible Titles", int(len(filtered_catalog)))
    summary_two.metric("Active Genre Filters", int(len(selected_genres)))

    display_columns = ["title", "year", "genres", "director", "overview"]
    st.dataframe(
        filtered_catalog[display_columns],
        use_container_width=True,
        hide_index=True,
    )


def render_credits_tab() -> None:
    st.markdown("### APIs, Credits, And Notes")
    overview_column, links_column = st.columns([1.2, 1])

    with overview_column:
        st.markdown(
            f"""
            <div class="tmdb-note">
              <p><strong>TMDB Attribution Notice</strong></p>
              <p>{TMDB_NOTICE}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.image(TMDB_LOGO_URL, width=120)
        st.write("The logo above uses TMDB's approved branding asset.")

        with st.container(border=True):
            st.markdown("#### Project Stack")
            st.write("Streamlit interface")
            st.write("Local TF-IDF + SVD + nearest-neighbor recommendation model")
            st.write("Optional TMDB live enrichment")
            st.write("Optional YouTube trailer search")

        with st.container(border=True):
            st.markdown("#### Local Setup")
            st.code(
                "TMDB_API_KEY=\nTMDB_ACCESS_TOKEN=\nYOUTUBE_API_KEY=\nYOUTUBE_REGION_CODE=IN",
                language="bash",
            )
            st.caption("You can keep keys in `.env`, `.streamlit/secrets.toml`, or the sidebar inputs.")

    with links_column:
        with st.container(border=True):
            st.markdown("#### Official Links")
            st.link_button("TMDB Website", TMDB_SITE_URL, use_container_width=True)
            st.link_button("TMDB FAQ", TMDB_FAQ_URL, use_container_width=True)
            st.link_button("TMDB Logos & Attribution", TMDB_LOGO_GUIDE_URL, use_container_width=True)
            st.link_button("YouTube", YOUTUBE_SITE_URL, use_container_width=True)
            st.link_button("YouTube Data API search docs", YOUTUBE_API_DOCS_URL, use_container_width=True)

        with st.container(border=True):
            st.markdown("#### Notes")
            st.write("The app stays fully usable before API keys are added.")
            st.write("You can replace the starter CSV later without redesigning the interface.")
            st.write("The saved model artifact will be reused when it is newer than the dataset.")


def main() -> None:
    inject_styles()
    tmdb_settings = build_tmdb_settings()
    youtube_settings = build_youtube_settings()
    render_sidebar_summary(tmdb_settings, youtube_settings)

    catalog = get_catalog(str(DATA_PATH))
    recommender = get_recommender(str(DATA_PATH), str(ARTIFACT_PATH))

    home_tab, discover_tab, catalog_tab, credits_tab = st.tabs(
        ["Home", "Discover", "Catalog", "Credits"]
    )

    with home_tab:
        render_home_tab(catalog, tmdb_settings, youtube_settings)

    with discover_tab:
        render_discover_tab(recommender, tmdb_settings, youtube_settings)

    with catalog_tab:
        render_catalog_tab(catalog)

    with credits_tab:
        render_credits_tab()


if __name__ == "__main__":
    main()
