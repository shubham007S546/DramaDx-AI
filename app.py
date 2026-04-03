from __future__ import annotations

import os
from difflib import SequenceMatcher
import unicodedata

import pandas as pd
import streamlit as st

from src import recommender
from src.config import (
    APP_SUBTITLE,
    APP_TITLE,
    DATA_PATH,
    DEFAULT_TMDB_LANGUAGE,
    DEFAULT_YOUTUBE_REGION,
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
    fetch_tv_profile_by_id,
)
from src.youtube import YouTubeSettings, build_youtube_search_url, fetch_video_result

st.set_page_config(page_title=APP_TITLE, page_icon="🎬", layout="wide")

COUNTRY_CODE_MAP = {"India": "IN", "Pakistan": "PK", "Turkey": "TR"}
COUNTRY_FLAGS    = {"India": "🇮🇳", "Pakistan": "🇵🇰", "Turkey": "🇹🇷"}

# Paths to CSVs
MOVIES_CSV      = os.path.join(os.path.dirname(DATA_PATH), "movies_seed.csv")
MOVIES_CAST_CSV = os.path.join(os.path.dirname(DATA_PATH), "movies_cast_seed.csv")


# ── Styles ───────────────────────────────────────────────────────────────────

def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=DM+Sans:wght@300;400;500;600&display=swap');

        :root {
            --bg:        #0a0c10;
            --surface:   #111318;
            --surface2:  #181c24;
            --border:    rgba(255,255,255,0.07);
            --accent:    #e8b86d;
            --accent2:   #c0392b;
            --text:      #e8e6e1;
            --muted:     #7a7a8a;
            --radius:    14px;
            --shadow:    0 8px 32px rgba(0,0,0,0.55);
        }

        html, body, .stApp {
            background: var(--bg) !important;
            font-family: 'DM Sans', sans-serif;
            color: var(--text);
        }
        .block-container { max-width: 1220px; padding-top: 0 !important; padding-bottom: 3rem; }

        .hero {
            position: relative; overflow: hidden;
            padding: 3rem 2.5rem 2.2rem; margin-bottom: 2rem;
            border-bottom: 1px solid var(--border);
            background: linear-gradient(135deg, #0d0f14 0%, #141820 60%, #1a1020 100%);
        }
        .hero::before {
            content: ''; position: absolute; inset: 0;
            background:
                radial-gradient(ellipse 60% 60% at 80% 50%, rgba(232,184,109,0.07) 0%, transparent 70%),
                radial-gradient(ellipse 40% 40% at 10% 20%, rgba(192,57,43,0.06) 0%, transparent 70%);
            pointer-events: none;
        }
        .hero-eyebrow { font-size:0.72rem; font-weight:600; letter-spacing:0.25em; text-transform:uppercase; color:var(--accent); margin-bottom:0.6rem; }
        .hero-title { font-family:'Playfair Display',Georgia,serif; font-size:clamp(2.2rem,5vw,3.6rem); font-weight:900; line-height:1.08; color:#fff; margin:0 0 0.75rem; letter-spacing:-0.02em; }
        .hero-title span { background:linear-gradient(90deg,var(--accent),#f5cfa0); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }
        .hero-sub { font-size:1.05rem; color:var(--muted); font-weight:300; max-width:560px; line-height:1.6; }

        .pill { display:inline-block; padding:0.22rem 0.7rem; border-radius:999px; font-size:0.72rem; font-weight:600; letter-spacing:0.05em; text-transform:uppercase; border:1px solid rgba(232,184,109,0.3); color:var(--accent); background:rgba(232,184,109,0.07); margin:0.15rem; }
        .pill-genre { border-color:rgba(120,180,255,0.25); color:#90c8ff; background:rgba(120,180,255,0.07); }
        .pill-theme { border-color:rgba(180,120,255,0.25); color:#c8a0ff; background:rgba(180,120,255,0.07); }
        .pill-movie { border-color:rgba(255,150,100,0.3); color:#ffaa77; background:rgba(255,150,100,0.08); }

        .metric-row { display:flex; gap:1rem; margin-bottom:1.5rem; }
        .metric-card { flex:1; background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:1.1rem 1.3rem; position:relative; overflow:hidden; }
        .metric-card::after { content:''; position:absolute; top:0;left:0;right:0; height:2px; background:linear-gradient(90deg,var(--accent),transparent); }
        .metric-label { font-size:0.7rem; letter-spacing:0.15em; text-transform:uppercase; color:var(--muted); margin-bottom:0.3rem; }
        .metric-value { font-family:'Playfair Display',serif; font-size:2rem; font-weight:700; color:var(--accent); line-height:1; }

        .section-label { font-size:0.68rem; letter-spacing:0.2em; text-transform:uppercase; color:var(--muted); margin:2rem 0 0.8rem; display:flex; align-items:center; gap:0.6rem; }
        .section-label::after { content:''; flex:1; height:1px; background:var(--border); }

        .poster-placeholder { aspect-ratio:2/3; background:linear-gradient(135deg,var(--surface2),#1e1a2e); border-radius:12px; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; border:1px dashed rgba(255,255,255,0.1); padding:1.5rem; color:var(--muted); font-size:0.85rem; }
        .poster-placeholder .icon { font-size:2.5rem; margin-bottom:0.5rem; opacity:0.4; }

        .drama-title { font-family:'Playfair Display',serif; font-size:clamp(1.6rem,3vw,2.4rem); font-weight:700; color:#fff; line-height:1.15; margin-bottom:0.3rem; }
        .drama-year { color:var(--accent); font-weight:400; }
        .drama-meta { font-size:0.82rem; color:var(--muted); margin-bottom:1rem; display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap; }
        .drama-meta .sep { opacity:0.3; }
        .overview { font-size:0.95rem; line-height:1.75; color:rgba(232,230,225,0.88); margin-bottom:1.2rem; border-left:3px solid var(--accent); padding-left:1rem; font-style:italic; }

        .rec-card { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; transition:transform 0.2s,border-color 0.2s; height:100%; }
        .rec-card:hover { transform:translateY(-3px); border-color:rgba(232,184,109,0.3); }
        .rec-card-body { padding:0.9rem; }
        .rec-title { font-family:'Playfair Display',serif; font-size:1rem; font-weight:700; color:#fff; margin-bottom:0.2rem; line-height:1.3; }
        .rec-meta { font-size:0.75rem; color:var(--muted); margin-bottom:0.5rem; }
        .rec-overview { font-size:0.8rem; color:rgba(200,198,194,0.75); line-height:1.55; }

        .featured-card { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); overflow:hidden; transition:transform 0.2s,box-shadow 0.2s; }
        .featured-card:hover { transform:translateY(-4px); box-shadow:0 16px 40px rgba(0,0,0,0.6); }
        .featured-body { padding:0.8rem; }
        .featured-title { font-family:'Playfair Display',serif; font-size:0.95rem; font-weight:700; color:#fff; }

        /* type badge */
        .type-badge { display:inline-block; padding:0.18rem 0.65rem; border-radius:999px; font-size:0.68rem; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; margin-left:0.5rem; vertical-align:middle; }
        .type-badge.movie { background:rgba(255,150,100,0.15); color:#ffaa77; border:1px solid rgba(255,150,100,0.3); }
        .type-badge.tv    { background:rgba(120,180,255,0.12); color:#90c8ff; border:1px solid rgba(120,180,255,0.25); }

        .stTextInput>div>div>input { background:var(--surface)!important; border:1px solid rgba(232,184,109,0.25)!important; border-radius:10px!important; color:var(--text)!important; font-family:'DM Sans',sans-serif!important; font-size:0.95rem!important; }
        .stTextInput>div>div>input:focus { border-color:var(--accent)!important; box-shadow:0 0 0 2px rgba(232,184,109,0.15)!important; }
        .stSelectbox>div>div { background:var(--surface)!important; border:1px solid var(--border)!important; border-radius:10px!important; }
        .stMultiSelect>div>div { background:var(--surface)!important; border:1px solid var(--border)!important; border-radius:10px!important; }
        .stButton>button,.stLinkButton>a { border-radius:10px!important; font-family:'DM Sans',sans-serif!important; font-weight:500!important; letter-spacing:0.02em!important; transition:all 0.2s!important; }
        .stLinkButton>a { background:var(--surface2)!important; border:1px solid var(--border)!important; color:var(--text)!important; }
        .stLinkButton>a:hover { border-color:var(--accent)!important; color:var(--accent)!important; }
        hr { border-color:var(--border)!important; }
        .streamlit-expanderHeader { background:var(--surface)!important; border-radius:var(--radius)!important; font-family:'DM Sans',sans-serif!important; }
        .stAlert { border-radius:10px!important; border-left-width:3px!important; }
        ::-webkit-scrollbar { width:6px; height:6px; }
        ::-webkit-scrollbar-track { background:var(--bg); }
        ::-webkit-scrollbar-thumb { background:#2a2d35; border-radius:3px; }
        ::-webkit-scrollbar-thumb:hover { background:var(--accent); }
        .status-dot { display:inline-block; width:7px; height:7px; border-radius:50%; background:#2ecc71; margin-right:5px; box-shadow:0 0 6px #2ecc71; }
        .status-dot.off { background:var(--muted); box-shadow:none; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def value(*names: str, default: str = "") -> str:
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


def split_tags(raw: object) -> list[str]:
    return [part.strip() for part in str(raw).split(",") if part and part.strip()]


def trim_text(value: object, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "…"


def normalize(text: object) -> str:
    raw = str(text or "").strip().lower()
    raw = raw.translate(str.maketrans({
        "ı": "i", "İ": "i", "ş": "s", "Ş": "s",
        "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u",
        "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
        "-": " ", "/": " ", ":": " ",
        "\u2018": "'", "\u2019": "'",
    }))
    normalized = unicodedata.normalize("NFKD", raw)
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    normalized = "".join(c if c.isalnum() or c.isspace() else " " for c in normalized)
    return " ".join(normalized.split())


def titles_match(left: object, right: object) -> bool:
    a = normalize(left)
    b = normalize(right)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.82


def profile_matches_record(profile: dict, record: dict) -> bool:
    candidates = [
        profile.get("title", ""),
        profile.get("original_title", ""),
        *split_tags(profile.get("aliases", "")),
    ]
    record_titles = [record.get("title", ""), *split_tags(record.get("aliases", ""))]
    return any(titles_match(l, r) for l in candidates for r in record_titles if l and r)


def merge_live_with_local(profile: dict, record: dict) -> dict:
    merged = dict(profile)
    if profile_matches_record(profile, record):
        merged["title"] = record.get("title", merged.get("title", ""))
    if record.get("poster_url") and not merged.get("poster_url"):
        merged["poster_url"] = record["poster_url"]
    if record.get("aliases"):
        alias_parts = []
        for candidate in [merged.get("aliases", ""), record.get("aliases", "")]:
            for alias in split_tags(candidate):
                if alias and alias not in alias_parts:
                    alias_parts.append(alias)
        merged["aliases"] = ", ".join(alias_parts)
    if record.get("themes"):
        merged["themes"] = split_tags(record["themes"])
    if record.get("network") and not merged.get("network"):
        merged["network"] = record["network"]
    if record.get("overview") and len(str(merged.get("overview", "")).strip()) < 40:
        merged["overview"] = record["overview"]
    return merged


def fix_country(x) -> str:
    """Normalise country field: ISO code → display name, unwrap lists."""
    try:
        if isinstance(x, list):
            x = x[0] if x else ""
        if x is None:
            return ""
        x = str(x).strip()
        return {"IN": "India", "PK": "Pakistan", "TR": "Turkey"}.get(x, x)
    except Exception:
        return ""


# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def get_catalog() -> pd.DataFrame:
    """Load TV dramas catalog and clean it up."""
    data = load_catalog(DATA_PATH)

    # Column renames
    rename_map = {}
    if "origin_country" in data.columns and "country" not in data.columns:
        rename_map["origin_country"] = "country"
    if "short_summary" in data.columns and "overview" not in data.columns:
        rename_map["short_summary"] = "overview"
    if "main_themes" in data.columns and "themes" not in data.columns:
        rename_map["main_themes"] = "themes"
    data = data.rename(columns=rename_map)

    if "country" not in data.columns:
        data["country"] = "Unknown"
    data["country"] = data["country"].apply(fix_country)

    if "year" not in data.columns:
        if "first_air_date" in data.columns:
            data["year"] = (
                pd.to_datetime(data["first_air_date"], errors="coerce")
                .dt.year.fillna(0).astype(int)
            )
        else:
            data["year"] = 0

    if "poster_url" not in data.columns:
        data["poster_url"] = ""

    data["_media_type"] = "tv"
    return data[(data["year"] >= 2020) & (data["year"] <= 2026)].reset_index(drop=True)


@st.cache_data(show_spinner=False)
def get_movies() -> pd.DataFrame:
    """Load movies CSV. Returns empty DataFrame if file not found."""
    if not os.path.exists(MOVIES_CSV):
        return pd.DataFrame()
    try:
        data = pd.read_csv(MOVIES_CSV, low_memory=False)
    except Exception:
        return pd.DataFrame()

    # Column renames to match TV schema
    rename_map = {}
    if "origin_country" in data.columns and "country" not in data.columns:
        rename_map["origin_country"] = "country"
    if "short_summary" in data.columns and "overview" not in data.columns:
        rename_map["short_summary"] = "overview"
    if "release_date" in data.columns and "first_air_date" not in data.columns:
        rename_map["release_date"] = "first_air_date"
    data = data.rename(columns=rename_map)

    if "country" not in data.columns:
        data["country"] = "Unknown"
    data["country"] = data["country"].apply(fix_country)

    if "year" not in data.columns:
        if "first_air_date" in data.columns:
            data["year"] = (
                pd.to_datetime(data["first_air_date"], errors="coerce")
                .dt.year.fillna(0).astype(int)
            )
        else:
            data["year"] = 0

    if "poster_url" not in data.columns:
        data["poster_url"] = ""
    if "overview" not in data.columns:
        data["overview"] = ""
    if "genres" not in data.columns:
        data["genres"] = ""
    if "network" not in data.columns:
        data["network"] = ""
    if "status" not in data.columns:
        data["status"] = ""
    if "language" not in data.columns:
        data["language"] = ""
    if "trailer_url" not in data.columns:
        data["trailer_url"] = ""
    if "keywords" not in data.columns:
        data["keywords"] = ""
    if "instagram_url" not in data.columns:
        data["instagram_url"] = ""
    if "twitter_url" not in data.columns:
        data["twitter_url"] = ""
    if "facebook_url" not in data.columns:
        data["facebook_url"] = ""
    if "runtime" not in data.columns:
        data["runtime"] = ""
    if "budget" not in data.columns:
        data["budget"] = ""
    if "revenue" not in data.columns:
        data["revenue"] = ""

    data["_media_type"] = "movie"
    return data[(data["year"] >= 2020) & (data["year"] <= 2026)].reset_index(drop=True)


@st.cache_data(show_spinner=False)
def get_movies_cast() -> pd.DataFrame:
    """Load movies cast CSV. Returns empty DataFrame if not found."""
    if not os.path.exists(MOVIES_CAST_CSV):
        return pd.DataFrame()
    try:
        return pd.read_csv(MOVIES_CAST_CSV, low_memory=False)
    except Exception:
        return pd.DataFrame()


@st.cache_data(show_spinner=False)
def get_combined_catalog() -> pd.DataFrame:
    """Merge TV dramas + movies into one searchable DataFrame."""
    tv     = get_catalog()
    movies = get_movies()
    if movies.empty:
        return tv
    # Align columns
    all_cols = list(dict.fromkeys(list(tv.columns) + list(movies.columns)))
    tv     = tv.reindex(columns=all_cols)
    movies = movies.reindex(columns=all_cols)
    combined = pd.concat([tv, movies], ignore_index=True)
    return combined.reset_index(drop=True)


@st.cache_resource(show_spinner=False)
def get_recommender() -> DramaRecommender:
    return DramaRecommender().fit(get_catalog())   # recommender trained on TV only (richer metadata)


# ── Fuzzy search across combined catalog ──────────────────────────────────────

def search_combined(query: str, catalog: pd.DataFrame,
                    countries: list[str], year_range: tuple[int, int],
                    media_types: list[str], limit: int = 8) -> list[dict]:
    """Simple fuzzy title search across the combined DataFrame."""
    if catalog.empty or not query:
        return []
    q_norm = normalize(query)
    rows   = catalog[
        catalog["country"].isin(countries) &
        catalog["year"].between(year_range[0], year_range[1]) &
        catalog["_media_type"].isin(media_types)
    ]
    results = []
    for _, row in rows.iterrows():
        title = str(row.get("title", "") or "")
        score = SequenceMatcher(None, q_norm, normalize(title)).ratio()
        if q_norm in normalize(title):
            score = max(score, 0.75)
        results.append((score, row.to_dict()))
    results.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in results if _ >= 0.30][:limit]


def browse_titles(catalog: pd.DataFrame, countries: list[str],
                  year_range: tuple[int, int], media_types: list[str]) -> list[str]:
    filtered = catalog[
        catalog["country"].isin(countries) &
        catalog["year"].between(year_range[0], year_range[1]) &
        catalog["_media_type"].isin(media_types)
    ]
    return sorted(filtered["title"].dropna().unique().tolist())


# ── API wrappers ──────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False, ttl=3600)
def tv_profile_by_title(title, country_code, year, api_key, access_token, language):
    settings = TMDBSettings(api_key=api_key, access_token=access_token, language=language)
    return fetch_tv_profile(
        query=title, settings=settings,
        preferred_country_code=country_code,
        year_range=(year, year) if year else None,
    )


@st.cache_data(show_spinner=False, ttl=3600)
def tv_profile_by_id(tv_id, api_key, access_token, language):
    settings = TMDBSettings(api_key=api_key, access_token=access_token, language=language)
    return fetch_tv_profile_by_id(tv_id=tv_id, settings=settings)


@st.cache_data(show_spinner=False, ttl=3600)
def person_profile(person_id, api_key, access_token, language):
    settings = TMDBSettings(api_key=api_key, access_token=access_token, language=language)
    return fetch_person_profile(person_id=person_id, settings=settings)


@st.cache_data(show_spinner=False, ttl=3600)
def youtube_watch(title, country, api_key, region_code):
    settings = YouTubeSettings(api_key=api_key, region_code=region_code)
    return fetch_video_result(title=title, country=country, settings=settings, mode="watch")


# ── Profile builders ──────────────────────────────────────────────────────────

def local_profile_tv(record: dict) -> dict:
    return {
        "source": "Starter catalog",
        "_media_type": "tv",
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
        "tmdb_id": int(record.get("tmdb_id", 0) or 0),
        "tmdb_url": build_tmdb_search_url(record.get("title", ""), media_type="tv"),
        "poster_url": record.get("poster_url", ""),
        "social_links": {},
        "cast": [
            {"name": n, "person_id": None, "character": "", "profile_url": ""}
            for n in split_tags(record.get("cast", ""))
        ],
    }


def local_profile_movie(record: dict) -> dict:
    """Build a profile dict from a movies_seed row."""
    return {
        "source": "Movies catalog",
        "_media_type": "movie",
        "title": record.get("title", ""),
        "original_title": record.get("original_title", record.get("title", "")),
        "year": int(record.get("year", 0) or 0),
        "country": record.get("country", ""),
        "language": record.get("language", ""),
        "status": record.get("status", "Released"),
        "genres": split_tags(record.get("genres", "")),
        "themes": [],
        "network": record.get("production_companies", ""),
        "overview": record.get("overview", ""),
        "aliases": "",
        "watch_hint": "",
        "tmdb_id": int(record.get("tmdb_id", 0) or 0),
        "tmdb_url": build_tmdb_search_url(record.get("title", ""), media_type="movie"),
        "poster_url": record.get("poster_url", ""),
        "runtime": record.get("runtime", ""),
        "budget": record.get("budget", ""),
        "revenue": record.get("revenue", ""),
        "social_links": {
            k: v for k, v in {
                "Instagram": record.get("instagram_url", ""),
                "Twitter":   record.get("twitter_url", ""),
                "Facebook":  record.get("facebook_url", ""),
            }.items() if v and isinstance(v, str) and v.strip().startswith("http")
        },
        "trailer_url": record.get("trailer_url", ""),
        "keywords":    record.get("keywords", ""),
        "cast": [],   # populated separately from movies_cast_seed.csv
    }


# ── Render helpers ────────────────────────────────────────────────────────────

def render_hero(catalog: pd.DataFrame, movies: pd.DataFrame, tmdb_live: bool) -> None:
    tmdb_dot = '<span class="status-dot"></span>' if tmdb_live else '<span class="status-dot off"></span>'
    st.markdown(
        f"""
        <div class="hero">
          <div class="hero-eyebrow">🎬 Drama & Movie Discovery Platform</div>
          <h1 class="hero-title">{APP_TITLE.split()[0]} <span>{" ".join(APP_TITLE.split()[1:])}</span></h1>
          <p class="hero-sub">{APP_SUBTITLE}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    n_movies = len(movies) if not movies.empty else 0
    st.markdown(
        f"""
        <div class="metric-row">
          <div class="metric-card">
            <div class="metric-label">TV Dramas</div>
            <div class="metric-value">{len(catalog)}</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Movies</div>
            <div class="metric-value">{n_movies}</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Countries</div>
            <div class="metric-value">{len(SUPPORTED_COUNTRIES)}</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Years Covered</div>
            <div class="metric-value">2020–26</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">TMDB Live</div>
            <div class="metric-value" style="font-size:1.1rem;padding-top:0.4rem">
              {tmdb_dot}{"Connected" if tmdb_live else "Optional"}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_featured_rows(combined: pd.DataFrame) -> None:
    featured = combined[
        combined["poster_url"].fillna("").astype(str).str.strip() != ""
    ].head(4)
    if featured.empty:
        return
    st.markdown('<div class="section-label">✦ Featured Picks</div>', unsafe_allow_html=True)
    cols = st.columns(len(featured))
    for idx, (_, row) in enumerate(featured.iterrows()):
        with cols[idx]:
            flag  = COUNTRY_FLAGS.get(row.get("country", ""), "")
            mtype = row.get("_media_type", "tv")
            badge = f'<span class="type-badge {"movie" if mtype=="movie" else "tv"}">{"🎬 Movie" if mtype=="movie" else "📺 TV"}</span>'
            st.markdown('<div class="featured-card">', unsafe_allow_html=True)
            st.image(row["poster_url"], use_container_width=True)
            st.markdown(
                f"""
                <div class="featured-body">
                  <div class="featured-title">{row['title']}{badge}</div>
                  <div style="font-size:0.75rem;color:var(--muted);margin-top:0.2rem">
                    {flag} {row.get('country','')} · {row.get('year','')}
                  </div>
                  <div style="font-size:0.78rem;color:rgba(200,198,194,0.7);margin-top:0.4rem;line-height:1.5">
                    {trim_text(row.get('overview',''), 90)}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown("</div>", unsafe_allow_html=True)


def render_profile(profile: dict, youtube_key: str, youtube_region: str) -> None:
    is_movie = profile.get("_media_type") == "movie"
    label    = "🎬 Selected Movie" if is_movie else "▶ Selected Drama"
    st.markdown(f'<div class="section-label">{label}</div>', unsafe_allow_html=True)

    left, right = st.columns([0.75, 1.5])

    with left:
        if profile.get("poster_url"):
            st.image(profile["poster_url"], use_container_width=True)
        else:
            flag = COUNTRY_FLAGS.get(profile.get("country", ""), "🎬")
            st.markdown(
                f"""
                <div class="poster-placeholder">
                  <div class="icon">{flag}</div>
                  <strong>{profile.get('title','')}</strong>
                  <span style="margin-top:0.3rem">{profile.get('country','')} · {profile.get('year','')}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with right:
        year   = profile.get("year", "")
        title  = profile.get("title", "Unknown")
        badge  = f'<span class="type-badge {"movie" if is_movie else "tv"}">{"🎬 Movie" if is_movie else "📺 TV Series"}</span>'
        st.markdown(
            f'<div class="drama-title">{title} <span class="drama-year">({year})</span>{badge}</div>',
            unsafe_allow_html=True,
        )

        if profile.get("original_title") and not titles_match(title, profile.get("original_title", "")):
            st.markdown(
                f'<div style="font-size:0.82rem;color:var(--muted);margin-bottom:0.5rem">Original: {profile["original_title"]}</div>',
                unsafe_allow_html=True,
            )

        flag = COUNTRY_FLAGS.get(profile.get("country", ""), "")
        meta_parts = [p for p in [
            f"{flag} {profile.get('country','')}" if profile.get("country") else "",
            profile.get("language", ""),
            profile.get("status", ""),
            f"⏱ {profile['runtime']} min" if profile.get("runtime") and is_movie else "",
            profile.get("network", "") if not is_movie else "",
        ] if p]
        st.markdown(
            sep = "<span class='sep'>•</span>"
            html = f'<div class="drama-meta">{sep.join(meta_parts)}</div>',
            unsafe_allow_html=True,
        )

        overview = profile.get("overview") or "No summary available."
        st.markdown(f'<div class="overview">{overview}</div>', unsafe_allow_html=True)

        # Movie financials
        if is_movie:
            fin_parts = []
            if profile.get("budget") and str(profile["budget"]) not in ("0", ""):
                try:
                    fin_parts.append(f"Budget: ${int(profile['budget']):,}")
                except Exception:
                    pass
            if profile.get("revenue") and str(profile["revenue"]) not in ("0", ""):
                try:
                    fin_parts.append(f"Box office: ${int(profile['revenue']):,}")
                except Exception:
                    pass
            if fin_parts:
                st.markdown(
                    f'<div style="font-size:0.82rem;color:var(--muted);margin-bottom:0.8rem">{" · ".join(fin_parts)}</div>',
                    unsafe_allow_html=True,
                )

        # Genre + theme pills
        pills_html = ""
        for g in profile.get("genres", []):
            pills_html += f'<span class="pill pill-genre">{g}</span>'
        for t in profile.get("themes", []):
            pills_html += f'<span class="pill pill-theme">{t}</span>'
        if is_movie:
            pills_html += '<span class="pill pill-movie">Movie</span>'
        if pills_html:
            st.markdown(pills_html, unsafe_allow_html=True)
            st.write("")

        if profile.get("aliases"):
            st.markdown(
                f'<div style="font-size:0.8rem;color:var(--muted);margin-top:0.3rem">Also known as: {profile["aliases"]}</div>',
                unsafe_allow_html=True,
            )
        if profile.get("watch_hint"):
            st.info(profile["watch_hint"])

        st.write("")
        btn_cols = st.columns(2)
        media_type_str = "movie" if is_movie else "tv"
        with btn_cols[0]:
            st.link_button(
                "🎬 Open on TMDB",
                profile.get("tmdb_url") or build_tmdb_search_url(title, media_type=media_type_str),
                use_container_width=True,
            )
        with btn_cols[1]:
            suffix = "official trailer" if is_movie else "official drama"
            st.link_button(
                "▶ Search YouTube",
                build_youtube_search_url(f"{title} {suffix}"),
                use_container_width=True,
            )

        # Official trailer (from TMDb videos, movies only)
        if is_movie and profile.get("trailer_url"):
            trailer = profile.get("trailer_url")

            if trailer and str(trailer).startswith("http"):
                st.link_button("🎬 Official Trailer", trailer, use_container_width=True)
            else:
                st.caption("Trailer not available")
            with st.expander("▶ Preview official trailer", expanded=False):
                trailer = profile.get("trailer_url")

                if trailer and isinstance(trailer, str) and trailer.startswith("http"):
                   st.video(trailer)
                else:
                   st.caption("Trailer not available")

        if youtube_key:
            video = youtube_watch(title, profile.get("country", ""), youtube_key, youtube_region)
            if video and video.get("watch_url"):
                st.link_button("🎯 Best YouTube Match", video["watch_url"], use_container_width=True)
                with st.expander("▶ Preview trailer", expanded=False):
                    st.video(video["watch_url"])
                    st.caption(f"{video.get('title','Video')} · {video.get('channel_title','YouTube')}")

        # Keywords pills (movies)
        if is_movie and profile.get("keywords"):
            kw_html = "".join(
                f'<span class="pill" style="font-size:0.65rem;opacity:0.8">{k.strip()}</span>'
                for k in str(profile["keywords"]).split(",")[:12] if k.strip()
            )
            if kw_html:
                st.markdown(f'<div style="margin-top:0.5rem">{kw_html}</div>', unsafe_allow_html=True)

        social_links = {
            lbl: url for lbl, url in (profile.get("social_links") or {}).items()
            if url and isinstance(url, str) and url.strip().startswith("http")
        }
        if social_links:
            st.markdown("**Official Links**")
            link_cols = st.columns(min(4, len(social_links)))
            for idx, (lbl, url) in enumerate(social_links.items()):
                link_cols[idx % len(link_cols)].link_button(lbl, url, use_container_width=True)
        else:
            st.caption("Official social links appear here when TMDB publishes them.")


def render_cast_explorer(profile: dict, tmdb_api_key, tmdb_access_token, tmdb_language) -> None:
    cast = profile.get("cast") or []
    if not cast:
        return
    st.markdown('<div class="section-label">👤 Cast</div>', unsafe_allow_html=True)
    cast_cols = st.columns(4)
    for idx, member in enumerate(cast[:8]):
        with cast_cols[idx % 4]:
            with st.container(border=True):
                img = member.get("profile_url")
                
                if img and str(img).lower() not in ["nan", "none", ""]:
                    st.image(img, use_container_width=True)
                else:
                    st.markdown(
                        '<div style="width:100%;aspect-ratio:2/3;background:var(--surface2);border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:2rem;opacity:0.4">👤</div>',
                        unsafe_allow_html=True,
                    )
                st.markdown(f"**{member.get('name','Cast member')}**")
                if member.get("character"):
                    st.caption(member["character"])

    labels, members_by_label = [], {}
    for member in cast[:12]:
        label = member.get("name", "Cast member")
        if member.get("character"):
            label = f"{label} — {member['character']}"
        labels.append(label)
        members_by_label[label] = member

    if not labels:
        return
    selected_label  = st.selectbox("🔍 Actor quick profile", options=labels)
    selected_member = members_by_label[selected_label]

    if not selected_member.get("person_id"):
        st.caption("Detailed actor metadata is not available for this entry.")
        return
    if not (tmdb_api_key or tmdb_access_token):
        st.caption("TMDB credentials are required for actor biographies.")
        return

    details = person_profile(int(selected_member["person_id"]), tmdb_api_key, tmdb_access_token, tmdb_language)
    if not details:
        st.caption("TMDB does not have a detailed person profile for this actor.")
        return

    bio_col, img_col = st.columns([1.4, 0.6])
    with bio_col:
        st.write(details.get("short_bio", "Biography unavailable."))
        extra = [p for p in [details.get("known_for", ""), details.get("place_of_birth", "")] if p]
        if extra:
            st.caption(" · ".join(extra))
        social = {
            lbl: url for lbl, url in (details.get("social_links") or {}).items()
            if url and isinstance(url, str) and url.strip().startswith("http")
        }
        if social:
            lc = st.columns(min(4, len(social)))
            for idx, (lbl, url) in enumerate(social.items()):
                lc[idx % len(lc)].link_button(lbl, url, use_container_width=True)
        else:
            st.caption("TMDB does not list public social handles for this actor.")
    with img_col:
        if details.get("profile_url"):
            st.image(details["profile_url"], use_container_width=True)


def render_recommendation_cards(rec: DramaRecommender, record: dict,
                                 combined: pd.DataFrame, is_movie: bool) -> None:
    st.markdown('<div class="section-label">✦ You Might Also Like</div>', unsafe_allow_html=True)

    recs = []

    if not is_movie:
        # Use the ML recommender for TV dramas
        try:
            recs = rec.recommend(record["title"], top_n=6)
        except Exception:
            pass

    if not recs:
        # Fallback: same country + overlapping genres, different title
        country = record.get("country", "")
        title   = record.get("title", "")
        genres  = set(split_tags(record.get("genres", "")))
        pool    = combined[
            (combined["country"] == country) &
            (combined["title"] != title) &
            (combined["_media_type"] == record.get("_media_type", "tv"))
        ]
        if genres:
            def genre_overlap(g):
                return len(genres & set(split_tags(g)))
            pool = pool.copy()
            pool["_score"] = pool["genres"].apply(genre_overlap)
            pool = pool.sort_values("_score", ascending=False)
        recs = pool.head(6).to_dict("records")

    if not recs:
        st.info("No similar titles found in the catalog.")
        return

    cols = st.columns(3)
    for idx, item in enumerate(recs[:6]):
        with cols[idx % 3]:
            flag  = COUNTRY_FLAGS.get(item.get("country", ""), "")
            mtype = item.get("_media_type", "tv")
            with st.container(border=True):
                if item.get("poster_url"):
                    poster = item.get("poster_url")

                    if poster and isinstance(poster, str) and poster.startswith("http"):
                        st.image(poster, use_container_width=True)
                    else:
                        st.markdown(
                            '<div style="width:100%;aspect-ratio:2/3;background:var(--surface2);border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:2rem;opacity:0.4">🎬</div>',
                            unsafe_allow_html=True,
                        )
                st.markdown(
                    f"""
                    <div class="rec-card-body">
                      <div class="rec-title">{item['title']}</div>
                      <div class="rec-meta">{flag} {item.get('country','')} · {item.get('year','')}
                        {'· 🎬 Movie' if mtype=='movie' else '· 📺 TV'}</div>
                      <div class="rec-overview">{trim_text(item.get('overview','No summary available.'), 110)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.link_button(
                    "Open TMDB",
                    build_tmdb_search_url(item.get("title", ""), media_type=mtype),
                    use_container_width=True,
                )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    inject_styles()

    tmdb_api_key      = value("TMDB_API_KEY")
    tmdb_access_token = value("TMDB_BEARER_TOKEN", "TMDB_ACCESS_TOKEN")
    tmdb_language     = value("TMDB_LANGUAGE", default=DEFAULT_TMDB_LANGUAGE)
    youtube_api_key   = value("YOUTUBE_API_KEY")
    youtube_region    = value("YOUTUBE_REGION_CODE", default=DEFAULT_YOUTUBE_REGION)
    tmdb_live         = bool(tmdb_api_key or tmdb_access_token)

    with st.spinner("Loading catalog…"):
        catalog  = get_catalog()
        movies   = get_movies()
        combined = get_combined_catalog()
    rec = get_recommender()

    render_hero(catalog, movies, tmdb_live)
    render_featured_rows(combined)
    st.divider()

    # ── Search & Filter ───────────────────────────────────────────────────
    st.markdown('<div class="section-label">🔍 Search & Filter</div>', unsafe_allow_html=True)

    search_col, country_col = st.columns([1.3, 1])
    with search_col:
        query = st.text_input(
            "Search dramas or movies",
            key="main_query",
            placeholder="Try: Dhurandhar, Tere Bin, Yargi, Bahar…",
        ).strip()
    with country_col:
        countries = st.multiselect(
            "Countries",
            options=list(SUPPORTED_COUNTRIES),
            default=list(SUPPORTED_COUNTRIES),
        )

    # Media type toggle
    media_type_opts = st.radio(
        "Show",
        options=["All", "📺 TV Dramas", "🎬 Movies"],
        horizontal=True,
        index=0,
    )
    media_types = (
        ["tv", "movie"] if media_type_opts == "All"
        else ["tv"]     if "TV" in media_type_opts
        else ["movie"]
    )

    year_min   = int(combined["year"].min()) if not combined.empty else 2020
    year_max   = int(combined["year"].max()) if not combined.empty else 2026
    year_range = st.slider("Year range", min_value=year_min, max_value=year_max, value=(year_min, year_max))

    active_countries = countries if countries else list(SUPPORTED_COUNTRIES)

    # ── Resolve title ─────────────────────────────────────────────────────
    if query:
        # Search combined catalog (TV + movies)
        matches = search_combined(query, combined, active_countries, year_range, media_types, limit=8)
        if matches:
            match_titles = [m["title"] for m in matches]
            if len(match_titles) == 1:
                selected_title = match_titles[0]
            else:
                selected_title = st.selectbox(
                    f"Best matches for '{query}'",
                    options=match_titles,
                    index=0,
                )
            # Find the full record
            record = next((m for m in matches if m["title"] == selected_title), matches[0])
        else:
            st.warning(f"No results found for **'{query}'** in the selected filters.")
            # Fallback to browse
            fallback_titles = browse_titles(combined, active_countries, year_range, media_types)
            if not fallback_titles:
                st.warning("No titles match the current filters.")
                st.stop()
            selected_title = st.selectbox("Browse instead", options=fallback_titles)
            rows = combined[combined["title"] == selected_title]
            record = rows.iloc[0].to_dict() if not rows.empty else {}
    else:
        fallback_titles = browse_titles(combined, active_countries, year_range, media_types)
        if not fallback_titles:
            st.warning("No titles match the current filters. Try widening your selection.")
            st.stop()
        selected_title = st.selectbox("Browse by title", options=fallback_titles)
        rows = combined[combined["title"] == selected_title]
        record = rows.iloc[0].to_dict() if not rows.empty else {}

    if not record:
        st.error("Could not load data for the selected title.")
        st.stop()

    is_movie = record.get("_media_type") == "movie"

    # ── Build profile ─────────────────────────────────────────────────────
    profile = None

    if tmdb_live and not is_movie:
        # Only fetch live TV profile from TMDB (movie live fetch can be added later)
        with st.spinner("Fetching live data from TMDB…"):
            profile = tv_profile_by_title(
                record.get("title", ""),
                COUNTRY_CODE_MAP.get(record.get("country", ""), None),
                int(record.get("year", 0) or 0),
                tmdb_api_key, tmdb_access_token, tmdb_language,
            )
            if profile and not profile_matches_record(profile, record):
                profile = None
            if not profile and int(record.get("tmdb_id", 0) or 0):
                profile = tv_profile_by_id(
                    int(record["tmdb_id"]), tmdb_api_key, tmdb_access_token, tmdb_language,
                )
                if profile and not profile_matches_record(profile, record):
                    profile = None

    if not profile:
        profile = local_profile_movie(record) if is_movie else local_profile_tv(record)
        if query and tmdb_live and not is_movie:
            st.warning("TMDB did not return a matching live drama. Showing catalog data.")
    elif not is_movie:
        profile = merge_live_with_local(profile, record)

    # ── Render ────────────────────────────────────────────────────────────
    render_profile(profile, youtube_api_key, youtube_region)
    if is_movie:
        # Inject cast from movies_cast_seed.csv into profile before rendering
        movies_cast_df = get_movies_cast()
        if not movies_cast_df.empty:
            tmdb_id = int(record.get("tmdb_id", 0) or 0)
            movie_cast_rows = movies_cast_df[movies_cast_df["tmdb_id"] == tmdb_id]
            if not movie_cast_rows.empty:
                profile["cast"] = [
                    {
                        "name":        str(row.get("name", "") or ""),
                        "character":   str(row.get("character_name", "") or ""),
                        "person_id":   row.get("tmdb_person_id"),
                        "profile_url": str(row.get("profile_url", "") or ""),
                    }
                    for _, row in movie_cast_rows.iterrows()
                ]
        render_cast_explorer(profile, tmdb_api_key, tmdb_access_token, tmdb_language)
    else:
        render_cast_explorer(profile, tmdb_api_key, tmdb_access_token, tmdb_language)
    render_recommendation_cards(rec, record, combined, is_movie)

    # ── Full catalog table ────────────────────────────────────────────────
    with st.expander("📋 Browse Full Catalog (TV + Movies)", expanded=False):
        display_cols = [c for c in ["title", "_media_type", "country", "year", "language",
                                     "status", "genres"] if c in combined.columns]
        st.dataframe(
            combined[display_cols].rename(columns={"_media_type": "type"}),
            use_container_width=True, hide_index=True,
        )

    # ── Attribution ───────────────────────────────────────────────────────
    with st.expander("⚙️ Setup & Attribution", expanded=False):
        st.info(TMDB_NOTICE)
        left_col, right_col = st.columns(2)
        with left_col:
            st.image(TMDB_LOGO_URL, width=120)
            st.link_button("TMDB Website", TMDB_SITE_URL, use_container_width=True)
            st.link_button("TMDB FAQ", TMDB_FAQ_URL, use_container_width=True)
            st.link_button("TMDB Attribution Guide", TMDB_LOGO_GUIDE_URL, use_container_width=True)
        with right_col:
            st.link_button("YouTube Data API Docs", YOUTUBE_API_DOCS_URL, use_container_width=True)
            st.link_button("YouTube", YOUTUBE_SITE_URL, use_container_width=True)
        st.caption("API keys are loaded privately from Streamlit secrets or environment variables.")


if __name__ == "__main__":
    main()