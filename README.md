# DramaDx AI

A Streamlit-first drama discovery app for Indian, Pakistani, and Turkish series. It works with the starter dataset right away, then becomes richer when you add TMDB and YouTube credentials.

What is included:

- interactive tabs for `Home`, `Search`, `Watchlist`, `Catalog`, and `Setup`
- starter drama catalog for offline search and recommendations
- local similarity model built with TF-IDF, SVD, and nearest neighbors
- optional TMDB live search for posters, cast details, social links, and drama profiles
- optional YouTube matching for watch links and quick video previews
- TMDB attribution and official reference links

## Project Structure

- `app.py` - main Streamlit application
- `src/data.py` - catalog loading and normalization
- `src/recommender.py` - local drama recommender and fuzzy search
- `src/tmdb.py` - TMDB live TV search and cast/profile helpers
- `src/youtube.py` - YouTube search helpers
- `scripts/train_model.py` - training and saving the recommendation artifact
- `data/dramas_seed.csv` - starter catalog

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create a local `.env` file from `.env.example` and add your TMDB and YouTube keys when you want live enrichment.

## Run The App

```powershell
python -m streamlit run app.py
```

## Optional Credentials

TMDB:

```powershell
$env:TMDB_API_KEY="your_key_here"
```

or

```powershell
$env:TMDB_ACCESS_TOKEN="your_access_token_here"
```

YouTube:

```powershell
$env:YOUTUBE_API_KEY="your_key_here"
```

You can also store the same keys in `.streamlit/secrets.toml`:

```toml
TMDB_API_KEY = "your_key_here"
TMDB_ACCESS_TOKEN = "your_access_token_here"
YOUTUBE_API_KEY = "your_key_here"
```

## Current UX

- `Home` gives quick picks, country-based browsing, and a fast way into search
- `Search` combines starter-catalog matching with optional TMDB live search
- `Watchlist` saves titles you want to revisit
- `Catalog` lets you filter and preview the starter dataset
- `Setup` explains the live-data requirements and attribution links

## Notes

- The starter dataset is intentionally small and can be replaced later with a larger ETL output.
- The recommender artifact retrains automatically when the CSV changes.
- TMDB is optional, but it unlocks the strongest version of the app.
- This project includes the required TMDB notice:

`This product uses the TMDB API but is not endorsed or certified by TMDB.`

Official references:

- [TMDB FAQ](https://developer.themoviedb.org/docs/faq)
- [TMDB Logos & Attribution](https://www.themoviedb.org/about/logos-attribution?language=en-US)
