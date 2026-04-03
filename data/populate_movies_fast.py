# -*- coding: utf-8 -*-
"""
populate_movies_fast.py  -  FULL MOVIE ENRICHMENT
==================================================
Fetches movies from TMDb for IN / PK / TR and enriches with:
  * Full movie details (runtime, budget, revenue, tagline, homepage)
  * Social links: Instagram, Twitter, Facebook for each movie
  * Cast list (top 15 per movie) with full person enrichment:
      - Age, birthday, birthplace, gender, biography
      - Instagram, Twitter, Facebook, TikTok links
      - IMDB, Wikidata IDs
      - Marriage/relationship status (via batched Wikidata SPARQL)
  * YouTube trailer link (via TMDb videos endpoint)
  * Keywords/themes for each movie

Outputs (in ./data/):
    movies_seed.csv        - one row per movie (enriched)
    movies_cast_seed.csv   - one row per cast member per movie
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import csv, time, os, threading
from pathlib import Path
from datetime import date, datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from tqdm import tqdm

# ==============================================================================
# 0.  CONFIG
# ==============================================================================
try:
    import tomllib
    with open(".streamlit/secrets.toml", "rb") as f:
        secrets = tomllib.load(f)
    API_KEY = secrets.get("TMDB_API_KEY", "")
except Exception:
    API_KEY = os.getenv("TMDB_API_KEY", "")

if not API_KEY:
    raise SystemExit(
        "ERROR: No TMDB_API_KEY found.\n"
        "Set it via:  export TMDB_API_KEY=your_key_here\n"
        "or add it to .streamlit/secrets.toml"
    )

BASE     = "https://api.themoviedb.org/3"
IMG_W500 = "https://image.tmdb.org/t/p/w500"
IMG_ORIG = "https://image.tmdb.org/t/p/original"

COUNTRIES             = ["IN", "PK", "TR"]
DATE_FROM             = "2020-01-01"
DATE_TO               = "2026-03-31"
MAX_PAGES_PER_COUNTRY = 10   # 10 pages × 20 results = up to 200 movies per country
MAX_CAST_PER_MOVIE    = 15
OUT_DIR               = Path("data")
OUT_DIR.mkdir(exist_ok=True)

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

# Parallelism
TMDB_WORKERS    = 8
PERSON_WORKERS  = 10
WIKI_BATCH_SIZE = 20
WIKI_TIMEOUT    = 12
WIKI_WORKERS    = 3
WIKI_MAX_FAILS  = 3
TMDB_SLEEP      = 0.1

# Set True to skip Wikidata (marriage info = "Unknown") — much faster
SKIP_WIKIDATA   = False

# ==============================================================================
# 1.  THREAD-SAFE HTTP
# ==============================================================================
_thread_local = threading.local()

def get_session() -> requests.Session:
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        s.headers.update({"Accept": "application/json"})
        _thread_local.session = s
    return _thread_local.session

def tmdb_get(endpoint: str, extra: dict = None, retries: int = 3) -> dict:
    params  = {"api_key": API_KEY, "language": "en-US", **(extra or {})}
    session = get_session()
    for attempt in range(retries):
        try:
            r = session.get(f"{BASE}{endpoint}", params=params, timeout=20)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 5))
                time.sleep(wait)
                continue
            r.raise_for_status()
            time.sleep(TMDB_SLEEP)
            return r.json()
        except requests.RequestException:
            if attempt == retries - 1:
                return {}
            time.sleep(2 ** attempt)
    return {}

def safe_tmdb_get(endpoint: str, extra: dict = None) -> dict:
    try:
        return tmdb_get(endpoint, extra)
    except Exception:
        return {}

# ==============================================================================
# 2.  HELPERS
# ==============================================================================
def genres_str(ids: list, genre_map: dict) -> str:
    return ", ".join(genre_map.get(i, "") for i in ids if genre_map.get(i))

def calculate_age(birthday: str) -> Optional[int]:
    if not birthday:
        return None
    try:
        bd    = datetime.strptime(birthday[:10], "%Y-%m-%d").date()
        today = date.today()
        return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    except ValueError:
        return None

def gender_label(g: int) -> str:
    return {0: "Unknown", 1: "Female", 2: "Male", 3: "Non-binary"}.get(g, "Unknown")

def safe_url(base_tpl: str, val: str) -> str:
    """Return formatted URL only if val is a non-empty string."""
    return base_tpl.format(val) if val and str(val).strip() else ""

# ==============================================================================
# 3.  WIKIDATA — parallel batched, resilient
# ==============================================================================
_wiki_cache   : dict           = {}
_wiki_lock                     = threading.Lock()
_wiki_gave_up                  = threading.Event()
_UNKNOWN_WIKI                  = {"marriage_status": "Unknown", "spouse_names": "", "partner_names": ""}

def _parse_wiki_bindings(qids: list, bindings: list) -> dict:
    raw = {}
    for b in bindings:
        pid = b["person"]["value"].split("/")[-1]
        if pid not in raw:
            raw[pid] = {"spouses": [], "divorced": False, "partners": []}
        if "spouseLabel" in b:
            raw[pid]["spouses"].append(b["spouseLabel"]["value"])
        if "divorceDate" in b:
            raw[pid]["divorced"] = True
        if "partnerLabel" in b:
            raw[pid]["partners"].append(b["partnerLabel"]["value"])
    out = {}
    for qid in qids:
        info     = raw.get(qid, {})
        spouses  = list(dict.fromkeys(info.get("spouses", [])))
        partners = list(dict.fromkeys(info.get("partners", [])))
        if info.get("divorced"):   status = "Divorced"
        elif spouses:              status = "Married"
        elif partners:             status = "In a relationship"
        else:                      status = "Unknown"
        out[qid] = {"marriage_status": status,
                    "spouse_names":    "; ".join(spouses),
                    "partner_names":   "; ".join(partners)}
    return out

def _fetch_one_wiki_batch(qids: list) -> dict:
    if _wiki_gave_up.is_set() or not qids:
        return {}
    values = " ".join(f"wd:{q}" for q in qids)
    sparql = f"""
    SELECT ?person ?spouseLabel ?divorceDate ?partnerLabel WHERE {{
      VALUES ?person {{ {values} }}
      OPTIONAL {{
        ?person wdt:P26 ?spouse .
        ?spouse rdfs:label ?spouseLabel FILTER(LANG(?spouseLabel)="en")
        OPTIONAL {{ ?person p:P26 ?stmt . ?stmt ps:P26 ?spouse ; pq:P582 ?divorceDate . }}
      }}
      OPTIONAL {{
        ?person wdt:P451 ?partner .
        ?partner rdfs:label ?partnerLabel FILTER(LANG(?partnerLabel)="en")
      }}
    }}
    """
    try:
        resp = requests.get(WIKIDATA_SPARQL,
                            params={"query": sparql, "format": "json"},
                            headers={"User-Agent": "movie-enricher/1.0"},
                            timeout=WIKI_TIMEOUT)
        resp.raise_for_status()
        return _parse_wiki_bindings(qids, resp.json().get("results", {}).get("bindings", []))
    except Exception:
        return {}

def prefetch_wikidata(wikidata_ids: list):
    if SKIP_WIKIDATA:
        print("  Wikidata skipped.")
        return
    ids = [q for q in wikidata_ids if q and q.startswith("Q") and q not in _wiki_cache]
    if not ids:
        return
    batches = [ids[i:i+WIKI_BATCH_SIZE] for i in range(0, len(ids), WIKI_BATCH_SIZE)]
    print(f"  Wikidata: {len(ids)} people → {len(batches)} batches (workers={WIKI_WORKERS})")
    consecutive_empty = 0
    with tqdm(total=len(ids), desc="  Wikidata", unit="people") as pbar:
        with ThreadPoolExecutor(max_workers=WIKI_WORKERS) as ex:
            for chunk_start in range(0, len(batches), WIKI_WORKERS * 2):
                if _wiki_gave_up.is_set():
                    break
                chunk = batches[chunk_start : chunk_start + WIKI_WORKERS * 2]
                futs  = {ex.submit(_fetch_one_wiki_batch, b): b for b in chunk}
                round_ok = False
                for fut in as_completed(futs):
                    batch  = futs[fut]
                    result = fut.result()
                    with _wiki_lock:
                        if result:
                            _wiki_cache.update(result)
                            round_ok = True
                        for qid in batch:
                            _wiki_cache.setdefault(qid, _UNKNOWN_WIKI.copy())
                    pbar.update(len(batch))
                if not round_ok:
                    consecutive_empty += 1
                    if consecutive_empty >= WIKI_MAX_FAILS:
                        print(f"\n  Wikidata gave up — remaining will be 'Unknown'.")
                        _wiki_gave_up.set()
                        with _wiki_lock:
                            for b in batches[chunk_start + WIKI_WORKERS * 2:]:
                                for qid in b:
                                    _wiki_cache.setdefault(qid, _UNKNOWN_WIKI.copy())
                        break
                else:
                    consecutive_empty = 0
                time.sleep(0.3)

def get_wiki_info(wikidata_id: str) -> dict:
    if not wikidata_id or not wikidata_id.startswith("Q"):
        return _UNKNOWN_WIKI.copy()
    with _wiki_lock:
        return _wiki_cache.get(wikidata_id, _UNKNOWN_WIKI.copy())

# ==============================================================================
# 4.  PERSON ENRICHMENT
# ==============================================================================
_person_cache : dict = {}
_person_lock         = threading.Lock()
_person_ext_map: dict = {}
_person_ext_lock     = threading.Lock()

def fetch_person_ext(pid: int):
    ext = safe_tmdb_get(f"/person/{pid}/external_ids")
    with _person_ext_lock:
        _person_ext_map[pid] = ext

def enrich_person(pid: int) -> dict:
    with _person_lock:
        if pid in _person_cache:
            return _person_cache[pid]

    p   = safe_tmdb_get(f"/person/{pid}")
    ext = _person_ext_map.get(pid) or safe_tmdb_get(f"/person/{pid}/external_ids")

    birthday     = p.get("birthday") or ""
    deathday     = p.get("deathday") or ""
    wikidata_id  = ext.get("wikidata_id") or ""
    instagram_id = ext.get("instagram_id") or ""
    twitter_id   = ext.get("twitter_id") or ""
    facebook_id  = ext.get("facebook_id") or ""
    tiktok_id    = ext.get("tiktok_id") or ""

    wiki_info = get_wiki_info(wikidata_id)

    result = {
        "tmdb_person_id":  pid,
        "name":            p.get("name", ""),
        "also_known_as":   " | ".join(p.get("also_known_as", [])[:5]),
        "gender":          gender_label(p.get("gender", 0)),
        "birthday":        birthday,
        "deathday":        deathday,
        "age":             calculate_age(birthday) if not deathday else None,
        "place_of_birth":  p.get("place_of_birth") or "",
        "nationality":     (p.get("place_of_birth") or "").split(",")[-1].strip(),
        "biography":       (p.get("biography") or "")[:800],
        "known_for_dept":  p.get("known_for_department") or "",
        "popularity":      round(p.get("popularity", 0), 2),
        "profile_url":     f"{IMG_W500}{p['profile_path']}" if p.get("profile_path") else "",
        "instagram_id":    instagram_id,
        "instagram_url":   safe_url("https://www.instagram.com/{}/", instagram_id),
        "twitter_id":      twitter_id,
        "twitter_url":     safe_url("https://twitter.com/{}", twitter_id),
        "facebook_id":     facebook_id,
        "facebook_url":    safe_url("https://www.facebook.com/{}", facebook_id),
        "tiktok_id":       tiktok_id,
        "tiktok_url":      safe_url("https://www.tiktok.com/@{}", tiktok_id),
        "imdb_id":         ext.get("imdb_id") or "",
        "wikidata_id":     wikidata_id,
        "marriage_status": wiki_info.get("marriage_status", "Unknown"),
        "spouse_names":    wiki_info.get("spouse_names", ""),
        "partner_names":   wiki_info.get("partner_names", ""),
    }
    with _person_lock:
        _person_cache[pid] = result
    return result

# ==============================================================================
# 5.  GENRE MAP
# ==============================================================================
print("Fetching genre list...")
movie_genre_map = {g["id"]: g["name"] for g in tmdb_get("/genre/movie/list").get("genres", [])}

# ==============================================================================
# 6.  DISCOVER MOVIES
# ==============================================================================
print("\nDiscovering movies (parallel page fetch)...")
movie_stubs   = []
seen_movie_ids = set()
stubs_lock     = threading.Lock()

def fetch_movie_page(country: str, page: int) -> tuple[list, int]:
    data = safe_tmdb_get("/discover/movie", {
        "with_origin_country":      country,
        "primary_release_date.gte": DATE_FROM,
        "primary_release_date.lte": DATE_TO,
        "sort_by":                  "popularity.desc",
        "page":                     page,
    })
    rows = []
    for r in data.get("results", []):
        with stubs_lock:
            if r["id"] in seen_movie_ids:
                continue
            seen_movie_ids.add(r["id"])
        rows.append((r, country))
    return rows, data.get("total_pages", 1)

for country in COUNTRIES:
    rows, total_pages = fetch_movie_page(country, 1)
    movie_stubs.extend(rows)
    max_page = min(total_pages, MAX_PAGES_PER_COUNTRY)
    with ThreadPoolExecutor(max_workers=TMDB_WORKERS) as ex:
        futs = {ex.submit(fetch_movie_page, country, p): p for p in range(2, max_page + 1)}
        for fut in as_completed(futs):
            r, _ = fut.result()
            movie_stubs.extend(r)
    print(f"  -> {sum(1 for _, c in movie_stubs if c == country)} stubs for {country}")

print(f"\nTotal unique movies discovered: {len(movie_stubs)}")

# ==============================================================================
# 7.  ENRICH EACH MOVIE IN PARALLEL
# ==============================================================================
def enrich_movie(stub: tuple) -> tuple[Optional[dict], list]:
    """Returns (movie_row, cast_partial_list)"""
    r, country = stub
    mid = r["id"]

    # Parallel fetch: details + external_ids + videos + keywords + credits
    with ThreadPoolExecutor(max_workers=5) as ex:
        f_md      = ex.submit(safe_tmdb_get, f"/movie/{mid}")
        f_ext     = ex.submit(safe_tmdb_get, f"/movie/{mid}/external_ids")
        f_videos  = ex.submit(safe_tmdb_get, f"/movie/{mid}/videos")
        f_kw      = ex.submit(safe_tmdb_get, f"/movie/{mid}/keywords")
        f_credits = ex.submit(safe_tmdb_get, f"/movie/{mid}/credits")
        md      = f_md.result()
        ext     = f_ext.result()
        videos  = f_videos.result()
        kw_data = f_kw.result()
        credits = f_credits.result()

    # YouTube trailer
    trailer_url = ""
    for v in videos.get("results", []):
        if v.get("site") == "YouTube" and v.get("type") in ("Trailer", "Teaser"):
            trailer_url = f"https://www.youtube.com/watch?v={v['key']}"
            break

    # Keywords
    keywords = ", ".join(
        k["name"] for k in kw_data.get("keywords", [])[:15]
    )

    # Genres
    raw_genres = md.get("genres", [])
    genre_str  = (
        genres_str([g["id"] for g in raw_genres], movie_genre_map)
        if raw_genres and isinstance(raw_genres[0], dict)
        else genres_str(r.get("genre_ids", []), movie_genre_map)
    )

    # Social links
    instagram_id = ext.get("instagram_id") or ""
    twitter_id   = ext.get("twitter_id") or ""
    facebook_id  = ext.get("facebook_id") or ""

    movie_row = {
        "tmdb_id":              mid,
        "title":                r.get("title", ""),
        "original_title":       r.get("original_title", ""),
        "release_date":         r.get("release_date", ""),
        "origin_country":       country,
        "language":             md.get("original_language") or "",
        "genres":               genre_str,
        "keywords":             keywords,
        "runtime":              md.get("runtime") or "",
        "short_summary":        (md.get("overview") or r.get("overview") or "")[:500],
        "tagline":              md.get("tagline") or "",
        "status":               md.get("status") or "",
        "budget":               md.get("budget") or "",
        "revenue":              md.get("revenue") or "",
        "production_companies": ", ".join(c["name"] for c in md.get("production_companies", [])[:3]),
        "production_countries": ", ".join(c["name"] for c in md.get("production_countries", [])[:3]),
        "poster_url":           f"{IMG_W500}{r['poster_path']}" if r.get("poster_path") else "",
        "backdrop_url":         f"{IMG_ORIG}{md['backdrop_path']}" if md.get("backdrop_path") else "",
        "homepage":             md.get("homepage") or "",
        "trailer_url":          trailer_url,
        "imdb_id":              ext.get("imdb_id") or "",
        "wikidata_id":          ext.get("wikidata_id") or "",
        "instagram_id":         instagram_id,
        "instagram_url":        safe_url("https://www.instagram.com/{}/", instagram_id),
        "twitter_id":           twitter_id,
        "twitter_url":          safe_url("https://twitter.com/{}", twitter_id),
        "facebook_id":          facebook_id,
        "facebook_url":         safe_url("https://www.facebook.com/{}", facebook_id),
        "popularity":           round(r.get("popularity", 0), 2),
        "vote_average":         round(r.get("vote_average", 0), 1),
        "vote_count":           r.get("vote_count", 0),
    }

    # Cast partial (person enrichment done separately)
    raw_cast     = credits.get("cast", [])[:MAX_CAST_PER_MOVIE]
    cast_partial = [
        {
            "tmdb_id":        mid,
            "movie_title":    r.get("title", ""),
            "character_name": m.get("character", ""),
            "billing_order":  m.get("order", ""),
            "tmdb_person_id": m.get("id"),
        }
        for m in raw_cast if m.get("id")
    ]

    return movie_row, cast_partial


print(f"Enriching {len(movie_stubs)} movies in parallel...")
movie_rows       = []
all_cast_partial = []

with ThreadPoolExecutor(max_workers=TMDB_WORKERS) as ex:
    futs = {ex.submit(enrich_movie, stub): stub for stub in movie_stubs}
    for fut in tqdm(as_completed(futs), total=len(futs), desc="Movies"):
        try:
            mrow, crows = fut.result()
            if mrow:
                movie_rows.append(mrow)
                all_cast_partial.extend(crows)
        except Exception as e:
            print(f"\n  WARN enrich_movie: {e}")

print(f"  -> {len(movie_rows)} movies enriched, {len(all_cast_partial)} cast entries collected")

# ==============================================================================
# 8.  ENRICH CAST — WIKIDATA BATCH THEN PARALLEL PERSON FETCH
# ==============================================================================
all_person_ids = list({c["tmdb_person_id"] for c in all_cast_partial if c["tmdb_person_id"]})
print(f"\nEnriching {len(all_person_ids)} unique cast members...")

# Step 1: External IDs in parallel
print("  Step 1/3: Fetching external IDs...")
with ThreadPoolExecutor(max_workers=PERSON_WORKERS) as ex:
    list(tqdm(ex.map(fetch_person_ext, all_person_ids),
              total=len(all_person_ids), desc="  ExtIDs"))

# Step 2: Wikidata batch
wikidata_ids = [_person_ext_map.get(pid, {}).get("wikidata_id", "") for pid in all_person_ids]
print("  Step 2/3: Batch-fetching Wikidata info...")
prefetch_wikidata([q for q in wikidata_ids if q and q.startswith("Q")])

# Step 3: Full person enrichment
print("  Step 3/3: Enriching person details...")
with ThreadPoolExecutor(max_workers=PERSON_WORKERS) as ex:
    list(tqdm(ex.map(enrich_person, all_person_ids),
              total=len(all_person_ids), desc="  Persons"))

# Assemble cast rows
all_cast_rows = []
for c in all_cast_partial:
    pid    = c["tmdb_person_id"]
    person = _person_cache.get(pid, {})
    all_cast_rows.append({**c, **person})

# ==============================================================================
# 9.  WRITE movies_seed.csv
# ==============================================================================
movie_fields = [
    "tmdb_id", "title", "original_title", "release_date", "origin_country",
    "language", "genres", "keywords", "runtime", "short_summary", "tagline", "status",
    "budget", "revenue", "production_companies", "production_countries",
    "poster_url", "backdrop_url", "homepage", "trailer_url",
    "imdb_id", "wikidata_id",
    "instagram_id", "instagram_url",
    "twitter_id",   "twitter_url",
    "facebook_id",  "facebook_url",
    "popularity", "vote_average", "vote_count",
]

out_movies = OUT_DIR / "movies_seed.csv"
with open(out_movies, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=movie_fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(movie_rows)
print(f"\n[OK] movies_seed.csv      -> {len(movie_rows)} movies")

# ==============================================================================
# 10.  WRITE movies_cast_seed.csv
# ==============================================================================
cast_fields = [
    "tmdb_id", "movie_title", "character_name", "billing_order",
    "tmdb_person_id", "name", "also_known_as", "gender",
    "birthday", "deathday", "age", "place_of_birth", "nationality",
    "known_for_dept", "biography",
    "marriage_status", "spouse_names", "partner_names",
    "profile_url",
    "instagram_id", "instagram_url",
    "twitter_id",   "twitter_url",
    "facebook_id",  "facebook_url",
    "tiktok_id",    "tiktok_url",
    "imdb_id", "wikidata_id",
    "popularity",
]

out_cast = OUT_DIR / "movies_cast_seed.csv"
with open(out_cast, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cast_fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(all_cast_rows)
print(f"[OK] movies_cast_seed.csv -> {len(all_cast_rows)} cast records ({len(_person_cache)} unique people)")

# ==============================================================================
# 11.  SUMMARY
# ==============================================================================
print("\n" + "=" * 55)
print("ALL DONE")
print("=" * 55)
print(f"  movies_seed.csv       {len(movie_rows):>5} movies")
print(f"  movies_cast_seed.csv  {len(all_cast_rows):>5} cast records")
print(f"  Unique cast members   {len(_person_cache):>5}")
print(f"\nFiles saved to: {OUT_DIR.resolve()}")
print("\nNext step: update app.py to load movies_cast_seed.csv for cast explorer on movie pages.")
