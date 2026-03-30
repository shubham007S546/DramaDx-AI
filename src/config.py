import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

DATA_PATH = ROOT_DIR / "data" / "movies_seed.csv"
ARTIFACT_PATH = ROOT_DIR / "artifacts" / "movie_recommender.joblib"

APP_TITLE = "CineMatch AI"
APP_SUBTITLE = "Streamlit + ML movie recommendations with optional TMDB live enrichment"
MODEL_NAME = "TF-IDF + SVD + Nearest Neighbors"

TMDB_NOTICE = "This product uses the TMDB API but is not endorsed or certified by TMDB."
TMDB_SITE_URL = "https://www.themoviedb.org/"
TMDB_FAQ_URL = "https://developer.themoviedb.org/docs/faq"
TMDB_LOGO_GUIDE_URL = "https://www.themoviedb.org/about/logos-attribution?language=en-US"
TMDB_LOGO_URL = (
    "https://www.themoviedb.org/assets/2/v4/logos/v2/blue_square_2-"
    "d537fb228cf3ded904ef09b136fe3fec72548ebc1fea3fbbd1ad9e36364db38b.svg"
)

DEFAULT_TMDB_LANGUAGE = os.getenv("TMDB_LANGUAGE", "en-US")

YOUTUBE_API_DOCS_URL = "https://developers.google.com/youtube/v3/docs/search/list"
YOUTUBE_SITE_URL = "https://www.youtube.com/"
DEFAULT_YOUTUBE_REGION = os.getenv("YOUTUBE_REGION_CODE", "IN")
