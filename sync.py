import argparse
import base64
import getpass
import json
import math
import os
import sys
import time
import zlib
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

# --- config ---

STREMIO_AUTH_KEY = os.getenv("STREMIO_AUTH_KEY", "")
SIMKL_CLIENT_ID = os.getenv("SIMKL_CLIENT_ID", "")
SIMKL_ACCESS_TOKEN = os.getenv("SIMKL_ACCESS_TOKEN", "")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")

STREMIO_API_URL = "https://api.strem.io/api"
SIMKL_API_URL = "https://api.simkl.com"
CINEMETA_URL = "https://v3-cinemeta.strem.io"

BATCH_SIZE = 50
API_DELAY = 1.0

# --- simkl ---

SIMKL_STATUSES = ["completed", "watching", "plantowatch"]
SIMKL_MEDIA_TYPES = ["movies", "shows", "anime"]
SIMKL_TOKEN_FILE = os.path.join(os.path.dirname(__file__), "simkl_token.json")
STREMIO_TOKEN_FILE = os.path.join(os.path.dirname(__file__), "stremio_token.json")


def simkl_headers():
    return {
        "Authorization": f"Bearer {SIMKL_ACCESS_TOKEN}",
        "simkl-api-key": SIMKL_CLIENT_ID,
        "Content-Type": "application/json",
    }


def simkl_authenticate_pin():
    resp = requests.get(
        f"{SIMKL_API_URL}/oauth/pin",
        params={"client_id": SIMKL_CLIENT_ID},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    print(f"Go to {data['verification_url']} and enter code: {data['user_code']}")

    start = time.time()
    while time.time() - start < data["expires_in"]:
        time.sleep(data.get("interval", 5))
        poll = requests.get(
            f"{SIMKL_API_URL}/oauth/pin/{data['user_code']}",
            params={"client_id": SIMKL_CLIENT_ID},
            timeout=10,
        )
        if poll.status_code == 200:
            token = poll.json()["access_token"]
            with open(SIMKL_TOKEN_FILE, "w") as f:
                json.dump({"access_token": token}, f)
            print("Simkl authentication successful!")
            return token

    raise TimeoutError("Simkl PIN authentication timed out")


def simkl_load_token():
    if SIMKL_ACCESS_TOKEN:
        return SIMKL_ACCESS_TOKEN
    if os.path.exists(SIMKL_TOKEN_FILE):
        with open(SIMKL_TOKEN_FILE) as f:
            return json.load(f)["access_token"]
    return None


def simkl_get_all_items():
    items = []
    for media_type in SIMKL_MEDIA_TYPES:
        for status in SIMKL_STATUSES:
            resp = requests.get(
                f"{SIMKL_API_URL}/sync/all-items/{media_type}/{status}",
                headers=simkl_headers(),
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


def simkl_normalize(raw_items, tmdb_api_key=None):
    """Normalize and aggregate Simkl items by IMDB ID, merging multi-season entries."""
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


# --- stremio ---

def stremio_login(email, password):
    resp = requests.post(
        f"{STREMIO_API_URL}/login",
        json={"email": email, "password": password, "facebook": False},
        timeout=10,
    )
    resp.raise_for_status()
    auth_key = resp.json()["result"]["authKey"]
    with open(STREMIO_TOKEN_FILE, "w") as f:
        json.dump({"authKey": auth_key}, f)
    print("Stremio login successful!")
    return auth_key


def stremio_load_auth_key():
    if STREMIO_AUTH_KEY:
        return STREMIO_AUTH_KEY
    if os.path.exists(STREMIO_TOKEN_FILE):
        with open(STREMIO_TOKEN_FILE) as f:
            return json.load(f)["authKey"]
    return None


def stremio_get_library():
    resp = requests.post(
        f"{STREMIO_API_URL}/datastoreGet",
        json={
            "authKey": STREMIO_AUTH_KEY,
            "collection": "libraryItem",
            "ids": [],
            "all": True,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("result", [])


def stremio_put_library(items):
    resp = requests.post(
        f"{STREMIO_API_URL}/datastorePut",
        json={
            "authKey": STREMIO_AUTH_KEY,
            "collection": "libraryItem",
            "changes": items,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def stremio_normalize(raw_items):
    result = {}
    for item in raw_items:
        imdb_id = item.get("_id", "")
        if not imdb_id.startswith("tt"):
            continue
        state = item.get("state", {})
        result[imdb_id] = {
            "imdb_id": imdb_id,
            "watched": state.get("timesWatched", 0) > 0 or state.get("flaggedWatched", 0) > 0,
            "removed": item.get("removed", False),
            "raw": item,
        }
    return result


def cinemeta_get_videos(imdb_id):
    resp = requests.get(f"{CINEMETA_URL}/meta/series/{imdb_id}.json", timeout=15)
    if resp.status_code != 200:
        return []
    videos = resp.json().get("meta", {}).get("videos", [])
    videos.sort(key=lambda v: (v.get("season", 0), v.get("episode", 0)))
    return videos


def build_watched_bitfield(total_videos, watched_indices):
    num_bytes = math.ceil(total_videos / 8) if total_videos > 0 else 1
    bitfield = bytearray(num_bytes)
    for idx in watched_indices:
        byte_pos = idx // 8
        bit_pos = 7 - (idx % 8)
        if byte_pos < len(bitfield):
            bitfield[byte_pos] |= (1 << bit_pos)
    return base64.b64encode(zlib.compress(bytes(bitfield))).decode()


def build_library_item(imdb_id, title, media_type, watched, status, watched_episodes=None):
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    ep_duration = 1440000 if media_type == "anime" else 2700000

    state = {
        "lastWatched": now if watched else None,
        "timeWatched": ep_duration if watched else 0,
        "timeOffset": 1 if watched else 0,
        "overallTimeWatched": ep_duration if watched else 0,
        "timesWatched": 1 if watched else 0,
        "flaggedWatched": 1 if watched else 0,
        "duration": ep_duration,
        "video_id": imdb_id if media_type == "movie" else None,
        "watched": None,
        "noNotif": False,
    }

    if media_type in ("series", "anime") and watched_episodes is not None:
        videos = cinemeta_get_videos(imdb_id)
        if videos:
            total = len(videos)
            count = min(watched_episodes, total)
            bitfield_b64 = build_watched_bitfield(total, set(range(count)))

            if count > 0:
                last = videos[count - 1]
                last_s, last_e = last.get("season", 1), last.get("episode", 1)
                state["video_id"] = f"{imdb_id}:{last_s}:{last_e}"
                state["watched"] = f"{imdb_id}:{last_s}:{last_e}:{total}:{bitfield_b64}"
                state["timesWatched"] = count
                state["flaggedWatched"] = count if watched else 0
                state["overallTimeWatched"] = ep_duration * count
                state["timeOffset"] = 1

    return {
        "_id": imdb_id,
        "name": title,
        "type": media_type,
        "poster": None,
        "posterShape": "poster",
        "removed": False,
        "temp": False,
        "_ctime": now,
        "_mtime": now,
        "state": state,
        "behaviorHints": {
            "defaultVideoId": None,
            "featuredVideoId": None,
            "hasScheduledVideos": False,
        },
    }


# --- sync ---

def compute_actions(simkl_items, stremio_items):
    actions = []
    for imdb_id, simkl in simkl_items.items():
        stremio = stremio_items.get(imdb_id)

        if stremio is None or stremio["removed"]:
            actions.append({**simkl, "action": "add"})
        elif simkl["watched"] and not stremio["watched"]:
            actions.append({**simkl, "action": "update"})
        elif (
            simkl["media_type"] in ("series", "anime")
            and simkl.get("watched_episodes", 0) > 1
            and not stremio["raw"].get("state", {}).get("watched")
        ):
            actions.append({**simkl, "action": "update"})

    return actions


def run_sync(dry_run=False):
    print("Fetching Simkl library...")
    raw_simkl = simkl_get_all_items()
    simkl_items = simkl_normalize(raw_simkl, tmdb_api_key=TMDB_API_KEY)
    print(f"  {len(simkl_items)} items from Simkl")

    print("Fetching Stremio library...")
    raw_stremio = stremio_get_library()
    stremio_items = stremio_normalize(raw_stremio)
    print(f"  {len(stremio_items)} items from Stremio")

    actions = compute_actions(simkl_items, stremio_items)
    adds = [a for a in actions if a["action"] == "add"]
    updates = [a for a in actions if a["action"] == "update"]
    skipped = len(simkl_items) - len(actions)

    print(f"\n{len(adds)} to add, {len(updates)} to update, {skipped} already in sync")

    if dry_run:
        for a in actions:
            print(f"  [{a['action']}] {a['title']} ({a['imdb_id']}) - {a['status']}")
        return {"added": 0, "updated": 0, "skipped": skipped}

    if not actions:
        return {"added": 0, "updated": 0, "skipped": skipped}

    changes = []
    for a in actions:
        watched_episodes = a.get("watched_episodes", 0) if a["media_type"] in ("series", "anime") else None
        item = build_library_item(
            imdb_id=a["imdb_id"],
            title=a["title"],
            media_type=a["media_type"],
            watched=a["watched"],
            status=a["status"],
            watched_episodes=watched_episodes,
        )
        if a["action"] == "update":
            existing = stremio_items[a["imdb_id"]]["raw"]
            item["_ctime"] = existing.get("_ctime", item["_ctime"])
            item["poster"] = existing.get("poster", item["poster"])
            item["name"] = existing.get("name", item["name"])
        changes.append(item)

    for i in range(0, len(changes), BATCH_SIZE):
        batch = changes[i : i + BATCH_SIZE]
        print(f"  Pushing batch {i // BATCH_SIZE + 1} ({len(batch)} items)...")
        stremio_put_library(batch)
        if i + BATCH_SIZE < len(changes):
            time.sleep(API_DELAY)

    print(f"\nDone: {len(adds)} added, {len(updates)} updated")
    return {"added": len(adds), "updated": len(updates), "skipped": skipped}


# --- cli ---

def main():
    global STREMIO_AUTH_KEY, SIMKL_ACCESS_TOKEN

    parser = argparse.ArgumentParser(description="Import Simkl library into Stremio")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    parser.add_argument("--simkl-auth", action="store_true", help="Run Simkl PIN authentication")
    parser.add_argument("--stremio-login", action="store_true", help="Login to Stremio with email/password")
    args = parser.parse_args()

    if args.stremio_login:
        email = input("Stremio email: ")
        password = getpass.getpass("Stremio password: ")
        STREMIO_AUTH_KEY = stremio_login(email, password)
        if not args.simkl_auth and not args.dry_run:
            return

    if args.simkl_auth:
        if not SIMKL_CLIENT_ID:
            print("Error: SIMKL_CLIENT_ID not set in .env")
            sys.exit(1)
        simkl_authenticate_pin()
        if not args.dry_run:
            return

    if not STREMIO_AUTH_KEY:
        STREMIO_AUTH_KEY = stremio_load_auth_key() or ""
    if not SIMKL_ACCESS_TOKEN:
        SIMKL_ACCESS_TOKEN = simkl_load_token() or ""

    missing = []
    if not STREMIO_AUTH_KEY:
        missing.append("STREMIO_AUTH_KEY (run --stremio-login or set in .env)")
    if not SIMKL_CLIENT_ID:
        missing.append("SIMKL_CLIENT_ID")
    if not SIMKL_ACCESS_TOKEN:
        missing.append("SIMKL_ACCESS_TOKEN (run --simkl-auth or set in .env)")
    if missing:
        print(f"Error: missing config:\n  " + "\n  ".join(missing))
        sys.exit(1)

    run_sync(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
