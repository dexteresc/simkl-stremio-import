import pytest


@pytest.fixture
def simkl_items():
    return {
        "tt1234567": {
            "imdb_id": "tt1234567",
            "title": "Test Movie",
            "media_type": "movie",
            "watched": True,
            "status": "completed",
        },
        "tt2222222": {
            "imdb_id": "tt2222222",
            "title": "Plan To Watch Movie",
            "media_type": "movie",
            "watched": False,
            "status": "plantowatch",
        },
        "tt3333333": {
            "imdb_id": "tt3333333",
            "title": "Watching Show",
            "media_type": "series",
            "watched": False,
            "status": "watching",
        },
    }


@pytest.fixture
def stremio_items():
    return {
        "tt1234567": {
            "imdb_id": "tt1234567",
            "watched": True,
            "removed": False,
            "raw": {
                "_id": "tt1234567",
                "name": "Test Movie",
                "type": "movie",
                "_ctime": "2024-01-01T00:00:00Z",
                "poster": "https://example.com/poster.jpg",
                "state": {"timesWatched": 1, "flaggedWatched": 1},
            },
        },
        "tt9999999": {
            "imdb_id": "tt9999999",
            "watched": True,
            "removed": False,
            "raw": {
                "_id": "tt9999999",
                "name": "Stremio Only Movie",
                "type": "movie",
                "_ctime": "2024-01-01T00:00:00Z",
                "state": {"timesWatched": 1, "flaggedWatched": 1},
            },
        },
    }


SIMKL_RAW_MOVIE = {
    "movie": {
        "title": "Raw Movie",
        "ids": {"simkl": 111, "imdb": "tt5555555", "tmdb": 555},
    },
    "simkl_status": "completed",
    "media_type": "movie",
}

SIMKL_RAW_SHOW = {
    "show": {
        "title": "Raw Show",
        "ids": {"simkl": 222, "imdb": "tt6666666", "tmdb": 666},
    },
    "simkl_status": "watching",
    "media_type": "series",
}

STREMIO_RAW_ITEM = {
    "_id": "tt7777777",
    "name": "Stremio Movie",
    "type": "movie",
    "poster": None,
    "posterShape": "poster",
    "removed": False,
    "temp": False,
    "_ctime": "2024-01-01T00:00:00Z",
    "_mtime": "2024-06-01T00:00:00Z",
    "state": {
        "lastWatched": "2024-06-01T00:00:00Z",
        "timeWatched": 7200000,
        "timeOffset": 7200000,
        "overallTimeWatched": 7200000,
        "timesWatched": 1,
        "flaggedWatched": 1,
        "duration": 7200000,
        "video_id": "tt7777777",
        "watched": None,
        "noNotif": False,
    },
    "behaviorHints": {
        "defaultVideoId": None,
        "featuredVideoId": None,
        "hasScheduledVideos": False,
    },
}
