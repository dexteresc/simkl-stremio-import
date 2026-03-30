import json
import os
import time

import requests

from . import config

TOKEN_FILE = os.path.join(os.path.dirname(__file__), "..", "simkl_token.json")

STATUSES = ["completed", "watching", "plantowatch"]
MEDIA_TYPES = ["movies", "shows", "anime"]


def _headers():
    return {
        "Authorization": f"Bearer {config.SIMKL_ACCESS_TOKEN}",
        "simkl-api-key": config.SIMKL_CLIENT_ID,
        "Content-Type": "application/json",
    }


def authenticate_pin():
    resp = requests.get(
        f"{config.SIMKL_API_URL}/oauth/pin",
        params={"client_id": config.SIMKL_CLIENT_ID},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    user_code = data["user_code"]
    verification_url = data["verification_url"]
    interval = data.get("interval", 5)
    expires_in = data["expires_in"]

    print(f"Go to {verification_url} and enter code: {user_code}")

    start = time.time()
    while time.time() - start < expires_in:
        time.sleep(interval)
        poll = requests.get(
            f"{config.SIMKL_API_URL}/oauth/pin/{user_code}",
            params={"client_id": config.SIMKL_CLIENT_ID},
            timeout=10,
        )
        if poll.status_code == 200:
            access_token = poll.json()["access_token"]
            with open(TOKEN_FILE, "w") as f:
                json.dump({"access_token": access_token}, f)
            print("Simkl authentication successful!")
            return access_token

    raise TimeoutError("Simkl PIN authentication timed out")


def load_token():
    if config.SIMKL_ACCESS_TOKEN:
        return config.SIMKL_ACCESS_TOKEN
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            return json.load(f)["access_token"]
    return None


def get_last_activities():
    resp = requests.get(
        f"{config.SIMKL_API_URL}/sync/activities",
        headers=_headers(),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def get_all_items():
    items = []
    for media_type in MEDIA_TYPES:
        for status in STATUSES:
            resp = requests.get(
                f"{config.SIMKL_API_URL}/sync/all-items/{media_type}/{status}",
                headers=_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            entry_list = data.get(media_type, []) if isinstance(data, dict) else data
            for item in entry_list:
                item["simkl_status"] = status
                item["media_type"] = "movie" if media_type == "movies" else "series"
                items.append(item)
    return items


def normalize_items(raw_items, tmdb_api_key=None):
    """Convert raw Simkl items to a dict keyed by IMDB ID.

    Aggregates watched episodes across multiple Simkl entries (e.g. separate
    seasons) that map to the same IMDB ID.
    """
    title_to_imdb = {}
    for item in raw_items:
        show = item.get("show") or item.get("movie") or item.get("anime") or item
        ids = show.get("ids", {})
        if ids.get("imdb"):
            title_to_imdb[show.get("title", "")] = ids["imdb"]

    entries = []
    for item in raw_items:
        show = item.get("show") or item.get("movie") or item.get("anime") or item
        ids = show.get("ids", {})
        imdb_id = ids.get("imdb")
        title = show.get("title", "Unknown")

        if not imdb_id and ids.get("tmdb") and tmdb_api_key:
            imdb_id = _resolve_imdb_from_tmdb(ids["tmdb"], tmdb_api_key)

        # match by longest title prefix to a known IMDB entry
        if not imdb_id:
            best_match = ""
            for known_title, known_imdb in title_to_imdb.items():
                if title.startswith(known_title) and len(known_title) > len(best_match):
                    best_match = known_title
                    imdb_id = known_imdb

        if not imdb_id:
            continue

        entries.append({
            "imdb_id": imdb_id,
            "title": title,
            "media_type": item.get("media_type", "movie"),
            "status": item.get("simkl_status", "completed"),
            "watched_episodes": item.get("watched_episodes_count", 0),
            "total_episodes": item.get("total_episodes_count", 0),
        })

    result = {}
    for entry in entries:
        imdb_id = entry["imdb_id"]
        if imdb_id not in result:
            result[imdb_id] = {
                "imdb_id": imdb_id,
                "title": entry["title"],
                "media_type": entry["media_type"],
                "watched": entry["status"] == "completed",
                "status": entry["status"],
                "watched_episodes": entry["watched_episodes"],
                "total_episodes": entry["total_episodes"],
            }
        else:
            existing = result[imdb_id]
            existing["watched_episodes"] += entry["watched_episodes"]
            existing["total_episodes"] += entry["total_episodes"]
            if entry["status"] == "completed" and existing["status"] == "completed":
                existing["watched"] = True

    return result


_tmdb_imdb_cache = {}


def _resolve_imdb_from_tmdb(tmdb_id, api_key):
    if tmdb_id in _tmdb_imdb_cache:
        return _tmdb_imdb_cache[tmdb_id]
    try:
        resp = requests.get(
            f"https://api.themoviedb.org/3/tv/{tmdb_id}/external_ids",
            params={"api_key": api_key},
            timeout=10,
        )
        if resp.status_code == 200:
            _tmdb_imdb_cache[tmdb_id] = resp.json().get("imdb_id")
            return _tmdb_imdb_cache[tmdb_id]
    except Exception:
        pass
    _tmdb_imdb_cache[tmdb_id] = None
    return None
