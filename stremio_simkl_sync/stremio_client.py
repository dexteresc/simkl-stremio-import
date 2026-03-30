import base64
import json
import math
import os
import zlib
from datetime import datetime, timezone

import requests

from . import config

CINEMETA_URL = "https://v3-cinemeta.strem.io"

TOKEN_FILE = os.path.join(os.path.dirname(__file__), "..", "stremio_token.json")


def login(email, password):
    resp = requests.post(
        f"{config.STREMIO_API_URL}/login",
        json={"email": email, "password": password, "facebook": False},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    auth_key = data["result"]["authKey"]
    with open(TOKEN_FILE, "w") as f:
        json.dump({"authKey": auth_key}, f)
    print("Stremio login successful!")
    return auth_key


def load_auth_key():
    if config.STREMIO_AUTH_KEY:
        return config.STREMIO_AUTH_KEY
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            return json.load(f)["authKey"]
    return None


def get_library():
    resp = requests.post(
        f"{config.STREMIO_API_URL}/datastoreGet",
        json={
            "authKey": config.STREMIO_AUTH_KEY,
            "collection": "libraryItem",
            "ids": [],
            "all": True,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("result", [])


def put_library(items):
    resp = requests.post(
        f"{config.STREMIO_API_URL}/datastorePut",
        json={
            "authKey": config.STREMIO_AUTH_KEY,
            "collection": "libraryItem",
            "changes": items,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def normalize_library(raw_items):
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


def get_cinemeta_videos(imdb_id, media_type="series"):
    resp = requests.get(
        f"{CINEMETA_URL}/meta/{media_type}/{imdb_id}.json",
        timeout=15,
    )
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
    compressed = zlib.compress(bytes(bitfield))
    return base64.b64encode(compressed).decode()


def build_library_item(imdb_id, title, media_type, watched, status,
                       watched_episodes=None):
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
        videos = get_cinemeta_videos(imdb_id, "series")
        if videos:
            total = len(videos)
            count = min(watched_episodes, total)
            watched_indices = set(range(count))
            bitfield_b64 = build_watched_bitfield(total, watched_indices)

            if count > 0:
                last_video = videos[count - 1]
                last_season = last_video.get("season", 1)
                last_episode = last_video.get("episode", 1)
                state["video_id"] = f"{imdb_id}:{last_season}:{last_episode}"
                state["watched"] = (
                    f"{imdb_id}:{last_season}:{last_episode}"
                    f":{total}:{bitfield_b64}"
                )
                state["timesWatched"] = count
                state["flaggedWatched"] = count if watched else 0
                state["overallTimeWatched"] = ep_duration * count
                state["timeOffset"] = 1

    item = {
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
    return item
