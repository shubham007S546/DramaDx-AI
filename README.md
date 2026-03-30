# DramaDx AI

A Streamlit-first starter project for a drama discovery and recommendation app, ready before the live API keys are added.

What is already included:

- Streamlit UI only, no separate backend/frontend stack
- Clean tabbed layout with `Home`, `Discover`, `Catalog`, and `Credits`
- ML recommendation model using TF-IDF + latent semantic reduction + nearest neighbors
- Starter movie catalog so recommendations work offline
- Optional TMDB enrichment for posters, ratings, and links after you add your key
- Optional YouTube trailer enrichment after you add a YouTube Data API key
- TMDB attribution block with the required notice and approved logo link

## Project Structure

- `app.py` - Streamlit application
- `src/data.py` - dataset loading and feature preparation
- `src/recommender.py` - ML recommendation model
- `src/tmdb.py` - optional TMDB API integration
- `src/youtube.py` - optional YouTube trailer integration
- `scripts/train_model.py` - training/saving the recommendation artifact
- `data/movies_seed.csv` - starter catalog

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create a local `.env` file from `.env.example` and add your own TMDB and YouTube keys before running live integrations.

## Train The Local Model

```powershell
python scripts/train_model.py
```

## Run The App

```powershell
python -m streamlit run app.py
```

## Add TMDB Later

The app already works without TMDB credentials. When you get your API access, you can either:

1. Put it in environment variables:

```powershell
$env:TMDB_API_KEY="your_key_here"
```

or

```powershell
$env:TMDB_ACCESS_TOKEN="your_access_token_here"
```

2. Keep it in private runtime secrets.

For local private storage with Streamlit, use:

```toml
# .streamlit/secrets.toml
TMDB_API_KEY = "your_key_here"
TMDB_ACCESS_TOKEN = "your_access_token_here"
YOUTUBE_API_KEY = "your_key_here"
```

This file is already ignored by git in this project.

## Add YouTube Trailers

The app can also show trailers for the selected movie and recommendations.

```powershell
$env:YOUTUBE_API_KEY="your_key_here"
```

You can also keep the YouTube key in private runtime secrets or environment variables.

## TMDB Attribution

This project already includes the required statement:

`This product uses the TMDB API but is not endorsed or certified by TMDB.`

Official TMDB references used for compliance:

- [TMDB FAQ](https://developer.themoviedb.org/docs/faq)
- [TMDB Logos & Attribution](https://www.themoviedb.org/about/logos-attribution?language=en-US)

## Notes

- You can replace `data/movies_seed.csv` with a larger catalog later.
- If the saved artifact is missing, the app can fit the recommender from the CSV automatically.
- Once you share your TMDB key, the same app will start pulling live posters and richer metadata.
- Once you add a YouTube key, the app can embed trailer links from the YouTube Data API.
- The `Home` tab is the landing page, `Discover` handles recommendations, `Catalog` is for browsing/filtering, and `Credits` keeps API links and attribution in one place.
