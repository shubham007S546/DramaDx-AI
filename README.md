# DramaDx AI

DramaDx AI is a Streamlit drama discovery app for Indian, Pakistani, and Turkish serials.

What is included now:

- Drama-first Streamlit UI with `Home`, `Search`, `Watchlist`, `Catalog`, and `Setup`
- Starter drama catalog for offline use
- Local similarity recommender for related drama suggestions
- TMDB TV search and detail integration for live posters, cast, social links, and actor mini-bios
- YouTube lookup support for official drama/trailer searches
- Private key handling through local `.env`, Streamlit secrets, or session-only sidebar inputs

## Project Structure

- `app.py` - Streamlit application
- `src/data.py` - drama catalog loading and normalization
- `src/recommender.py` - local drama recommender
- `src/tmdb.py` - TMDB TV search, detail, cast, and person profile integration
- `src/youtube.py` - YouTube search helper
- `scripts/train_model.py` - trains and saves the local recommender artifact
- `data/dramas_seed.csv` - starter drama dataset

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create a local `.env` file from `.env.example` if you want live TMDB or YouTube enrichment.

## Run The App

```powershell
python -m streamlit run app.py
```

## Local Private Keys

Keep keys only on your machine.

```env
TMDB_BEARER_TOKEN=your_tmdb_token
TMDB_API_KEY=your_tmdb_api_key_optional
YOUTUBE_API_KEY=your_youtube_key
OMDB_API_KEY=your_omdb_key_optional
TMDB_LANGUAGE=en-US
YOUTUBE_REGION_CODE=IN
```

You can also use `.streamlit/secrets.toml` or the session-only sidebar fields.

## Current Behavior

- Without keys:
  - the app still works with the starter drama catalog
  - search, recommendations, watchlist, and fallback links still work
  - posters are replaced by styled placeholders
- With TMDB:
  - live TV drama results
  - real posters
  - richer cast
  - actor short bios
  - social handles when available
- With YouTube:
  - best-match watch/trailer result buttons

## Notes

- The starter dataset is only a bootstrap layer, not the final 2020-2026 production dataset.
- Replace `data/dramas_seed.csv` later with your ETL output for full coverage.
- The recommender artifact retrains automatically when the dataset changes.

## TMDB Attribution

`This product uses the TMDB API but is not endorsed or certified by TMDB.`

Official references:

- [TMDB FAQ](https://developer.themoviedb.org/docs/faq)
- [TMDB Logos & Attribution](https://www.themoviedb.org/about/logos-attribution?language=en-US)
