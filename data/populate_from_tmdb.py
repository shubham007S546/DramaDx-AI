# -*- coding: utf-8 -*-
"""
populate_from_tmdb_fast.py  -  OPTIMIZED VERSION
=================================================
Key speedups over original:
  * ThreadPoolExecutor for parallel TMDb API calls (person enrichment, show enrichment)
  * Batched Wikidata SPARQL (fetch up to 50 people per query instead of 1-by-1)
  * Adaptive rate limiting with a token-bucket style semaphore
  * Wikidata calls skipped if they keep timing out (auto-backoff)
  * Reduced sleep times where safe
  * Progress bars show real ETA
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
MAX_PAGES_PER_COUNTRY = 15
MAX_CAST_PER_SHOW     = 15
OUT_DIR               = Path("data")
OUT_DIR.mkdir(exist_ok=True)

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

# Parallelism settings — tune these if you hit 429s
TMDB_WORKERS      = 8   # parallel threads for TMDb calls
PERSON_WORKERS    = 10  # parallel threads for person enrichment
WIKI_BATCH_SIZE   = 20  # people per Wikidata SPARQL batch (smaller = less timeout risk)
WIKI_TIMEOUT      = 12  # seconds per Wikidata request
WIKI_WORKERS      = 3   # parallel Wikidata batch fetchers (don't set too high)
WIKI_MAX_FAILS    = 3   # give up on Wikidata after this many consecutive failures
TMDB_SLEEP        = 0.1 # seconds between TMDb calls per thread (safe ~80 req/s total)

# Set to True to skip Wikidata entirely (marriage/relationship will be "Unknown")
SKIP_WIKIDATA     = False

# ==============================================================================
# 1.  THREAD-SAFE SESSION POOL
# ==============================================================================
_thread_local = threading.local()
_rate_lock    = threading.Lock()
_last_call    = [0.0]  # shared last-call time for gentle global rate limiting


def get_session() -> requests.Session:
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        s.headers.update({"Accept": "application/json"})
        _thread_local.session = s
    return _thread_local.session


def tmdb_get(endpoint: str, extra: dict = None, retries: int = 3) -> dict:
    params = {"api_key": API_KEY, "language": "en-US", **(extra or {})}
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
        bd = datetime.strptime(birthday[:10], "%Y-%m-%d").date()
        today = date.today()
        return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    except ValueError:
        return None


def gender_label(g: int) -> str:
    return {0: "Unknown", 1: "Female", 2: "Male", 3: "Non-binary"}.get(g, "Unknown")


# ==============================================================================
# 3.  WIKIDATA — PARALLEL BATCHED, RESILIENT
# ==============================================================================
_wiki_cache: dict      = {}
_wiki_lock             = threading.Lock()
_wiki_gave_up          = threading.Event()   # set → stop all further Wikidata work
_UNKNOWN_WIKI          = {"marriage_status": "Unknown", "spouse_names": "", "partner_names": ""}


def _parse_wiki_bindings(qids: list[str], bindings: list) -> dict[str, dict]:
    raw: dict[str, dict] = {}
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
        if info.get("divorced"):
            status = "Divorced"
        elif spouses:
            status = "Married"
        elif partners:
            status = "In a relationship"
        else:
            status = "Unknown"
        out[qid] = {"marriage_status": status,
                    "spouse_names":    "; ".join(spouses),
                    "partner_names":   "; ".join(partners)}
    return out


def _fetch_one_batch(qids: list[str]) -> dict[str, dict]:
    """Single SPARQL call for a batch of QIDs. Returns {} on any failure."""
    if _wiki_gave_up.is_set() or not qids:
        return {}
    values = " ".join(f"wd:{q}" for q in qids)
    sparql = f"""
    SELECT ?person ?spouseLabel ?divorceDate ?partnerLabel WHERE {{
      VALUES ?person {{ {values} }}
      OPTIONAL {{
        ?person wdt:P26 ?spouse .
        ?spouse rdfs:label ?spouseLabel FILTER(LANG(?spouseLabel)="en")
        OPTIONAL {{ ?person p:P26 ?stmt .
                   ?stmt ps:P26 ?spouse ; pq:P582 ?divorceDate . }}
      }}
      OPTIONAL {{
        ?person wdt:P451 ?partner .
        ?partner rdfs:label ?partnerLabel FILTER(LANG(?partnerLabel)="en")
      }}
    }}
    """
    try:
        resp = requests.get(
            WIKIDATA_SPARQL,
            params={"query": sparql, "format": "json"},
            headers={"User-Agent": "drama-recommender/1.0"},
            timeout=WIKI_TIMEOUT,
        )
        resp.raise_for_status()
        return _parse_wiki_bindings(qids, resp.json().get("results", {}).get("bindings", []))
    except Exception:
        return {}   # caller handles failure counting


def prefetch_wikidata_batch(wikidata_ids: list[str]):
    """
    Parallel-batch fetch Wikidata marriage info.
    - Splits IDs into chunks of WIKI_BATCH_SIZE
    - Runs WIKI_WORKERS chunks in parallel
    - Gives up after WIKI_MAX_FAILS consecutive all-failed rounds
    """
    if SKIP_WIKIDATA:
        print("  Wikidata skipped (SKIP_WIKIDATA=True).")
        return

    ids_to_fetch = [q for q in wikidata_ids if q and q.startswith("Q") and q not in _wiki_cache]
    if not ids_to_fetch:
        return

    batches = [ids_to_fetch[i:i+WIKI_BATCH_SIZE]
               for i in range(0, len(ids_to_fetch), WIKI_BATCH_SIZE)]
    total   = len(ids_to_fetch)
    print(f"  Wikidata: {total} people → {len(batches)} batches "
          f"(size={WIKI_BATCH_SIZE}, workers={WIKI_WORKERS})")

    consecutive_empty = 0

    with tqdm(total=total, desc="  Wikidata", unit="people") as pbar:
        with ThreadPoolExecutor(max_workers=WIKI_WORKERS) as ex:
            # Submit in round groups so we can detect consecutive failures
            for chunk_start in range(0, len(batches), WIKI_WORKERS * 2):
                if _wiki_gave_up.is_set():
                    break
                chunk = batches[chunk_start : chunk_start + WIKI_WORKERS * 2]
                futs  = {ex.submit(_fetch_one_batch, b): b for b in chunk}
                round_ok = False
                for fut in as_completed(futs):
                    batch = futs[fut]
                    result = fut.result()
                    with _wiki_lock:
                        if result:
                            _wiki_cache.update(result)
                            round_ok = True
                        # Mark anything not returned as Unknown (don't retry)
                        for qid in batch:
                            if qid not in _wiki_cache:
                                _wiki_cache[qid] = _UNKNOWN_WIKI.copy()
                    pbar.update(len(batch))

                if not round_ok:
                    consecutive_empty += 1
                    if consecutive_empty >= WIKI_MAX_FAILS:
                        print(f"\n  Wikidata gave up after {WIKI_MAX_FAILS} failed rounds "
                              f"— remaining cast will have marriage_status='Unknown'.")
                        _wiki_gave_up.set()
                        # Mark all remaining as Unknown immediately
                        with _wiki_lock:
                            for b in batches[chunk_start + WIKI_WORKERS * 2:]:
                                for qid in b:
                                    _wiki_cache.setdefault(qid, _UNKNOWN_WIKI.copy())
                        break
                else:
                    consecutive_empty = 0
                time.sleep(0.3)  # polite gap between rounds


def get_wiki_info(wikidata_id: str) -> dict:
    if not wikidata_id or not wikidata_id.startswith("Q"):
        return _UNKNOWN_WIKI.copy()
    with _wiki_lock:
        return _wiki_cache.get(wikidata_id, _UNKNOWN_WIKI.copy())


# ==============================================================================
# 4.  PERSON ENRICHMENT — parallel
# ==============================================================================
_person_cache: dict = {}
_person_lock  = threading.Lock()


def enrich_person(tmdb_person_id: int) -> dict:
    with _person_lock:
        if tmdb_person_id in _person_cache:
            return _person_cache[tmdb_person_id]

    # Fetch person + external IDs in parallel
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_person = ex.submit(safe_tmdb_get, f"/person/{tmdb_person_id}")
        f_ext    = ex.submit(safe_tmdb_get, f"/person/{tmdb_person_id}/external_ids")
        p   = f_person.result()
        ext = f_ext.result()

    birthday    = p.get("birthday") or ""
    deathday    = p.get("deathday") or ""
    wikidata_id = ext.get("wikidata_id") or ""

    instagram_id  = ext.get("instagram_id") or ""
    twitter_id    = ext.get("twitter_id") or ""
    facebook_id   = ext.get("facebook_id") or ""
    tiktok_id     = ext.get("tiktok_id") or ""

    wiki_info = get_wiki_info(wikidata_id)

    result = {
        "tmdb_person_id":  tmdb_person_id,
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
        "instagram_url":   f"https://www.instagram.com/{instagram_id}/" if instagram_id else "",
        "twitter_id":      twitter_id,
        "twitter_url":     f"https://twitter.com/{twitter_id}" if twitter_id else "",
        "facebook_id":     facebook_id,
        "facebook_url":    f"https://www.facebook.com/{facebook_id}" if facebook_id else "",
        "tiktok_id":       tiktok_id,
        "tiktok_url":      f"https://www.tiktok.com/@{tiktok_id}" if tiktok_id else "",
        "imdb_id":         ext.get("imdb_id") or "",
        "wikidata_id":     wikidata_id,
        "marriage_status": wiki_info.get("marriage_status", "Unknown"),
        "spouse_names":    wiki_info.get("spouse_names", ""),
        "partner_names":   wiki_info.get("partner_names", ""),
    }

    with _person_lock:
        _person_cache[tmdb_person_id] = result
    return result


# ==============================================================================
# 5.  GENRE MAPS
# ==============================================================================
print("Fetching genre lists...")
tv_genre_map    = {g["id"]: g["name"] for g in tmdb_get("/genre/tv/list").get("genres", [])}
movie_genre_map = {g["id"]: g["name"] for g in tmdb_get("/genre/movie/list").get("genres", [])}


# ==============================================================================
# 6.  DISCOVER TV SHOWS (parallel per-country page fetching)
# ==============================================================================
drama_rows = []
seen_ids   = set()
seen_lock  = threading.Lock()


def fetch_tv_page(country: str, page: int) -> list[dict]:
    data = safe_tmdb_get("/discover/tv", {
        "with_origin_country": country,
        "first_air_date.gte":  DATE_FROM,
        "first_air_date.lte":  DATE_TO,
        "sort_by":             "popularity.desc",
        "page":                page,
    })
    rows = []
    for r in data.get("results", []):
        with seen_lock:
            if r["id"] in seen_ids:
                continue
            seen_ids.add(r["id"])
        rows.append({
            "tmdb_id":        r["id"],
            "title":          r.get("name", ""),
            "original_title": r.get("original_name", ""),
            "first_air_date": r.get("first_air_date", ""),
            "origin_country": country,
            "popularity":     round(r.get("popularity", 0), 2),
            "vote_average":   round(r.get("vote_average", 0), 1),
            "vote_count":     r.get("vote_count", 0),
            "poster_url":     f"{IMG_W500}{r['poster_path']}" if r.get("poster_path") else "",
            "overview":       r.get("overview", ""),
            "_total_pages":   data.get("total_pages", 1),
        })
    return rows, data.get("total_pages", 1)


print("\nDiscovering TV shows (parallel)...")
for country in COUNTRIES:
    # Fetch page 1 first to know total_pages
    rows, total_pages = fetch_tv_page(country, 1)
    drama_rows.extend(rows)
    max_page = min(total_pages, MAX_PAGES_PER_COUNTRY)

    futures = {}
    with ThreadPoolExecutor(max_workers=TMDB_WORKERS) as ex:
        for page in range(2, max_page + 1):
            futures[ex.submit(fetch_tv_page, country, page)] = page
        for fut in as_completed(futures):
            r, _ = fut.result()
            drama_rows.extend(r)

    country_count = sum(1 for d in drama_rows if d["origin_country"] == country)
    print(f"  -> {country_count} shows found for {country}")


# ==============================================================================
# 7.  ENRICH SHOWS IN PARALLEL
# ==============================================================================
def enrich_show(row: dict) -> tuple[dict, list[dict], list[dict]]:
    """Returns (enriched_row, season_rows, cast_rows_partial)"""
    tid = row["tmdb_id"]

    # Fetch show detail + external IDs in parallel
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_d   = ex.submit(safe_tmdb_get, f"/tv/{tid}")
        f_ext = ex.submit(safe_tmdb_get, f"/tv/{tid}/external_ids")
        d   = f_d.result()
        ext = f_ext.result()

    show_instagram_id = ext.get("instagram_id") or ""
    show_twitter_id   = ext.get("twitter_id") or ""
    show_facebook_id  = ext.get("facebook_id") or ""

    row.update({
        "language":             d.get("original_language", ""),
        "genres":               genres_str([g["id"] for g in d.get("genres", [])], tv_genre_map),
        "status":               d.get("status", ""),
        "type":                 d.get("type", ""),
        "last_air_date":        d.get("last_air_date") or "",
        "seasons":              d.get("number_of_seasons", ""),
        "episodes":             d.get("number_of_episodes", ""),
        "episode_runtime":      ", ".join(str(x) for x in d.get("episode_run_time", [])),
        "network":              ", ".join(n["name"] for n in d.get("networks", [])[:3]),
        "production_companies": ", ".join(c["name"] for c in d.get("production_companies", [])[:3]),
        "created_by":           ", ".join(c["name"] for c in d.get("created_by", [])),
        "short_summary":        (d.get("overview") or "")[:500],
        "backdrop_url":         f"{IMG_ORIG}{d['backdrop_path']}" if d.get("backdrop_path") else "",
        "homepage":             d.get("homepage") or "",
        "in_production":        d.get("in_production", ""),
        "tagline":              d.get("tagline") or "",
        "imdb_id":              ext.get("imdb_id") or "",
        "wikidata_id":          ext.get("wikidata_id") or "",
        "instagram_id":         show_instagram_id,
        "instagram_url":        f"https://www.instagram.com/{show_instagram_id}/" if show_instagram_id else "",
        "twitter_id":           show_twitter_id,
        "twitter_url":          f"https://twitter.com/{show_twitter_id}" if show_twitter_id else "",
        "facebook_id":          show_facebook_id,
        "facebook_url":         f"https://www.facebook.com/{show_facebook_id}" if show_facebook_id else "",
    })

    # Seasons
    season_rows = []
    for season in d.get("seasons", []):
        season_rows.append({
            "tmdb_id":       tid,
            "show_title":    row["title"],
            "season_number": season.get("season_number", 0),
            "season_name":   season.get("name", ""),
            "air_date":      season.get("air_date") or "",
            "episode_count": season.get("episode_count", ""),
            "poster_url":    f"{IMG_W500}{season['poster_path']}" if season.get("poster_path") else "",
            "overview":      (season.get("overview") or "")[:300],
            "season_id":     season.get("id", ""),
        })

    # Cast (partial — person enrichment done separately)
    credits  = safe_tmdb_get(f"/tv/{tid}/credits")
    raw_cast = credits.get("cast", [])[:MAX_CAST_PER_SHOW]
    cast_partial = [
        {
            "tmdb_id":        tid,
            "show_title":     row["title"],
            "character_name": m.get("character", ""),
            "billing_order":  m.get("order", ""),
            "tmdb_person_id": m.get("id"),
        }
        for m in raw_cast if m.get("id")
    ]

    return row, season_rows, cast_partial


print(f"\nEnriching {len(drama_rows)} TV shows in parallel...")
enriched_dramas  = []
all_season_rows  = []
all_cast_partial = []  # will enrich persons separately

with ThreadPoolExecutor(max_workers=TMDB_WORKERS) as ex:
    futures = {ex.submit(enrich_show, row): row for row in drama_rows}
    for fut in tqdm(as_completed(futures), total=len(futures), desc="Shows"):
        try:
            erow, srows, crows = fut.result()
            enriched_dramas.append(erow)
            all_season_rows.extend(srows)
            all_cast_partial.extend(crows)
        except Exception as e:
            print(f"\n  WARN enrich_show: {e}")


# ==============================================================================
# 8.  BATCH-FETCH WIKIDATA FOR ALL CAST, THEN ENRICH PERSONS IN PARALLEL
# ==============================================================================
all_person_ids = list({c["tmdb_person_id"] for c in all_cast_partial if c["tmdb_person_id"]})
print(f"\nEnriching {len(all_person_ids)} unique cast members...")

# Step 1: Collect all wikidata IDs via parallel external_ids fetch
print("  Step 1/3: Fetching external IDs for all persons...")
person_ext_map: dict[int, dict] = {}
person_ext_lock = threading.Lock()

def fetch_person_ext(pid: int):
    ext = safe_tmdb_get(f"/person/{pid}/external_ids")
    with person_ext_lock:
        person_ext_map[pid] = ext

with ThreadPoolExecutor(max_workers=PERSON_WORKERS) as ex:
    list(tqdm(ex.map(fetch_person_ext, all_person_ids), total=len(all_person_ids), desc="  ExtIDs"))

# Step 2: Batch-fetch all Wikidata info
wikidata_ids_for_cast = [
    person_ext_map.get(pid, {}).get("wikidata_id", "")
    for pid in all_person_ids
]
print("  Step 2/3: Batch-fetching Wikidata marriage/relationship info...")
prefetch_wikidata_batch([q for q in wikidata_ids_for_cast if q and q.startswith("Q")])

# Step 3: Enrich all persons in parallel (Wikidata already cached)
print("  Step 3/3: Enriching person details in parallel...")

def enrich_person_fast(pid: int) -> dict:
    with _person_lock:
        if pid in _person_cache:
            return _person_cache[pid]

    p   = safe_tmdb_get(f"/person/{pid}")
    ext = person_ext_map.get(pid) or safe_tmdb_get(f"/person/{pid}/external_ids")

    birthday    = p.get("birthday") or ""
    deathday    = p.get("deathday") or ""
    wikidata_id = ext.get("wikidata_id") or ""
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
        "instagram_url":   f"https://www.instagram.com/{instagram_id}/" if instagram_id else "",
        "twitter_id":      twitter_id,
        "twitter_url":     f"https://twitter.com/{twitter_id}" if twitter_id else "",
        "facebook_id":     facebook_id,
        "facebook_url":    f"https://www.facebook.com/{facebook_id}" if facebook_id else "",
        "tiktok_id":       tiktok_id,
        "tiktok_url":      f"https://www.tiktok.com/@{tiktok_id}" if tiktok_id else "",
        "imdb_id":         ext.get("imdb_id") or "",
        "wikidata_id":     wikidata_id,
        "marriage_status": wiki_info.get("marriage_status", "Unknown"),
        "spouse_names":    wiki_info.get("spouse_names", ""),
        "partner_names":   wiki_info.get("partner_names", ""),
    }
    with _person_lock:
        _person_cache[pid] = result
    return result


with ThreadPoolExecutor(max_workers=PERSON_WORKERS) as ex:
    list(tqdm(ex.map(enrich_person_fast, all_person_ids), total=len(all_person_ids), desc="  Persons"))

# Assemble final cast rows
all_cast_rows = []
for c in all_cast_partial:
    pid = c["tmdb_person_id"]
    person = _person_cache.get(pid, {})
    all_cast_rows.append({**c, **person})


# ==============================================================================
# 9.  WRITE CSVs
# ==============================================================================
drama_fields = [
    "tmdb_id", "title", "original_title", "language", "genres", "status", "type",
    "first_air_date", "last_air_date", "seasons", "episodes", "episode_runtime",
    "network", "production_companies", "created_by",
    "short_summary", "tagline", "homepage", "in_production",
    "poster_url", "backdrop_url",
    "imdb_id", "wikidata_id",
    "instagram_id", "instagram_url", "twitter_id", "twitter_url",
    "facebook_id", "facebook_url",
    "popularity", "vote_average", "vote_count", "origin_country",
]
with open(OUT_DIR / "dramas_seed.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=drama_fields, extrasaction="ignore")
    w.writeheader(); w.writerows(enriched_dramas)
print(f"\n[OK] dramas_seed.csv   -> {len(enriched_dramas)} shows")

season_fields = [
    "tmdb_id", "show_title", "season_number", "season_name",
    "air_date", "episode_count", "overview", "poster_url", "season_id",
]
with open(OUT_DIR / "seasons_seed.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=season_fields, extrasaction="ignore")
    w.writeheader(); w.writerows(all_season_rows)
print(f"[OK] seasons_seed.csv  -> {len(all_season_rows)} season records")

cast_fields = [
    "tmdb_id", "show_title", "character_name", "billing_order",
    "tmdb_person_id", "name", "also_known_as", "gender",
    "birthday", "deathday", "age", "place_of_birth", "nationality",
    "known_for_dept", "biography",
    "marriage_status", "spouse_names", "partner_names",
    "profile_url",
    "instagram_id", "instagram_url",
    "twitter_id", "twitter_url",
    "facebook_id", "facebook_url",
    "tiktok_id", "tiktok_url",
    "imdb_id", "wikidata_id",
    "popularity",
]
with open(OUT_DIR / "cast_seed.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cast_fields, extrasaction="ignore")
    w.writeheader(); w.writerows(all_cast_rows)
print(f"[OK] cast_seed.csv     -> {len(all_cast_rows)} cast records ({len(_person_cache)} unique people)")


# ==============================================================================
# 10.  MOVIES (parallel)
# ==============================================================================
print("\nFetching movies in parallel...")
movie_rows     = []
seen_movie_ids = set()
movie_lock     = threading.Lock()


def fetch_and_enrich_movie(r: dict, country: str) -> Optional[dict]:
    mid = r["id"]
    with movie_lock:
        if mid in seen_movie_ids:
            return None
        seen_movie_ids.add(mid)

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_md  = ex.submit(safe_tmdb_get, f"/movie/{mid}")
        f_ext = ex.submit(safe_tmdb_get, f"/movie/{mid}/external_ids")
        md  = f_md.result()
        ext = f_ext.result()

    raw_genres = md.get("genres", [])
    genre_str = (
        genres_str([g["id"] for g in raw_genres], movie_genre_map)
        if raw_genres and isinstance(raw_genres[0], dict)
        else genres_str(r.get("genre_ids", []), movie_genre_map)
    )
    instagram_id = ext.get("instagram_id") or ""
    twitter_id   = ext.get("twitter_id") or ""

    return {
        "tmdb_id":              mid,
        "title":                r.get("title", ""),
        "original_title":       r.get("original_title", ""),
        "release_date":         r.get("release_date", ""),
        "origin_country":       country,
        "language":             md.get("original_language") or "",
        "genres":               genre_str,
        "runtime":              md.get("runtime") or "",
        "short_summary":        (md.get("overview") or r.get("overview") or "")[:400],
        "tagline":              md.get("tagline") or "",
        "status":               md.get("status") or "",
        "budget":               md.get("budget") or "",
        "revenue":              md.get("revenue") or "",
        "production_companies": ", ".join(c["name"] for c in md.get("production_companies", [])[:3]),
        "poster_url":           f"{IMG_W500}{r['poster_path']}" if r.get("poster_path") else "",
        "backdrop_url":         f"{IMG_ORIG}{md['backdrop_path']}" if md.get("backdrop_path") else "",
        "homepage":             md.get("homepage") or "",
        "imdb_id":              ext.get("imdb_id") or "",
        "wikidata_id":          ext.get("wikidata_id") or "",
        "instagram_id":         instagram_id,
        "instagram_url":        f"https://www.instagram.com/{instagram_id}/" if instagram_id else "",
        "twitter_id":           twitter_id,
        "twitter_url":          f"https://twitter.com/{twitter_id}" if twitter_id else "",
        "popularity":           round(r.get("popularity", 0), 2),
        "vote_average":         round(r.get("vote_average", 0), 1),
        "vote_count":           r.get("vote_count", 0),
    }


# Collect all movie stubs first
movie_stubs = []
for country in COUNTRIES:
    for page in range(1, 6):
        data = safe_tmdb_get("/discover/movie", {
            "with_origin_country":      country,
            "primary_release_date.gte": DATE_FROM,
            "primary_release_date.lte": DATE_TO,
            "sort_by":                  "popularity.desc",
            "page":                     page,
        })
        for r in data.get("results", []):
            movie_stubs.append((r, country))
        if page >= data.get("total_pages", 1):
            break

# Enrich all movies in parallel
with ThreadPoolExecutor(max_workers=TMDB_WORKERS) as ex:
    futures = [ex.submit(fetch_and_enrich_movie, r, c) for r, c in movie_stubs]
    for fut in tqdm(as_completed(futures), total=len(futures), desc="Movies"):
        result = fut.result()
        if result:
            movie_rows.append(result)

movie_fields = [
    "tmdb_id", "title", "original_title", "release_date", "origin_country",
    "language", "genres", "runtime", "short_summary", "tagline", "status",
    "budget", "revenue", "production_companies",
    "poster_url", "backdrop_url", "homepage",
    "imdb_id", "wikidata_id",
    "instagram_id", "instagram_url", "twitter_id", "twitter_url",
    "popularity", "vote_average", "vote_count",
]
with open(OUT_DIR / "movies_seed.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=movie_fields, extrasaction="ignore")
    w.writeheader(); w.writerows(movie_rows)
print(f"[OK] movies_seed.csv   -> {len(movie_rows)} movies")


# ==============================================================================
# 11.  SUMMARY
# ==============================================================================
print("\n" + "=" * 55)
print("ALL DONE")
print("=" * 55)
print(f"  dramas_seed.csv   {len(enriched_dramas):>5} TV shows")
print(f"  seasons_seed.csv  {len(all_season_rows):>5} season records")
print(f"  cast_seed.csv     {len(all_cast_rows):>5} cast records  ({len(_person_cache)} unique people)")
print(f"  movies_seed.csv   {len(movie_rows):>5} movies")
print("\nNext step:  python scripts/train_model.py")