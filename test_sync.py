import json

import pytest
import responses

import sync


# --- fixtures ---

FAKE_AUTH_KEY = "test-stremio-auth-key"
FAKE_SIMKL_CLIENT_ID = "test-simkl-client-id"
FAKE_SIMKL_TOKEN = "test-simkl-token"


@pytest.fixture(autouse=True)
def _set_config():
    sync.STREMIO_AUTH_KEY = FAKE_AUTH_KEY
    sync.SIMKL_CLIENT_ID = FAKE_SIMKL_CLIENT_ID
    sync.SIMKL_ACCESS_TOKEN = FAKE_SIMKL_TOKEN
    sync.TMDB_API_KEY = ""


@pytest.fixture
def simkl_items():
    return {
        "tt1234567": {
            "imdb_id": "tt1234567", "title": "Test Movie",
            "media_type": "movie", "watched": True, "status": "completed",
        },
        "tt2222222": {
            "imdb_id": "tt2222222", "title": "Plan To Watch Movie",
            "media_type": "movie", "watched": False, "status": "plantowatch",
        },
        "tt3333333": {
            "imdb_id": "tt3333333", "title": "Watching Show",
            "media_type": "series", "watched": False, "status": "watching",
        },
    }


@pytest.fixture
def stremio_items():
    return {
        "tt1234567": {
            "imdb_id": "tt1234567", "watched": True, "removed": False,
            "raw": {"_id": "tt1234567", "name": "Test Movie", "type": "movie",
                    "_ctime": "2024-01-01T00:00:00Z", "poster": "https://example.com/poster.jpg",
                    "state": {"timesWatched": 1, "flaggedWatched": 1}},
        },
        "tt9999999": {
            "imdb_id": "tt9999999", "watched": True, "removed": False,
            "raw": {"_id": "tt9999999", "name": "Stremio Only Movie", "type": "movie",
                    "_ctime": "2024-01-01T00:00:00Z",
                    "state": {"timesWatched": 1, "flaggedWatched": 1}},
        },
    }


SIMKL_RAW_MOVIE = {
    "movie": {"title": "Raw Movie", "ids": {"simkl": 111, "imdb": "tt5555555", "tmdb": 555}},
    "simkl_status": "completed", "media_type": "movie",
}

SIMKL_RAW_SHOW = {
    "show": {"title": "Raw Show", "ids": {"simkl": 222, "imdb": "tt6666666", "tmdb": 666}},
    "simkl_status": "watching", "media_type": "series",
}

STREMIO_RAW_ITEM = {
    "_id": "tt7777777", "name": "Stremio Movie", "type": "movie",
    "poster": None, "posterShape": "poster", "removed": False, "temp": False,
    "_ctime": "2024-01-01T00:00:00Z", "_mtime": "2024-06-01T00:00:00Z",
    "state": {
        "lastWatched": "2024-06-01T00:00:00Z", "timeWatched": 7200000,
        "timeOffset": 7200000, "overallTimeWatched": 7200000,
        "timesWatched": 1, "flaggedWatched": 1, "duration": 7200000,
        "video_id": "tt7777777", "watched": None, "noNotif": False,
    },
    "behaviorHints": {"defaultVideoId": None, "featuredVideoId": None, "hasScheduledVideos": False},
}


# --- unit tests ---

class TestComputeActions:
    def test_new_item_added(self, simkl_items, stremio_items):
        actions = sync.compute_actions(simkl_items, stremio_items)
        added_ids = {a["imdb_id"] for a in actions if a["action"] == "add"}
        assert "tt2222222" in added_ids
        assert "tt3333333" in added_ids

    def test_already_synced_skipped(self, simkl_items, stremio_items):
        action_ids = {a["imdb_id"] for a in sync.compute_actions(simkl_items, stremio_items)}
        assert "tt1234567" not in action_ids

    def test_watched_state_update(self, simkl_items, stremio_items):
        stremio_items["tt2222222"] = {
            "imdb_id": "tt2222222", "watched": False, "removed": False,
            "raw": {"_id": "tt2222222", "name": "Plan To Watch Movie", "_ctime": "2024-01-01T00:00:00Z"},
        }
        simkl_items["tt2222222"]["watched"] = True
        simkl_items["tt2222222"]["status"] = "completed"
        updates = [a for a in sync.compute_actions(simkl_items, stremio_items) if a["imdb_id"] == "tt2222222"]
        assert len(updates) == 1
        assert updates[0]["action"] == "update"

    def test_stremio_only_ignored(self, simkl_items, stremio_items):
        action_ids = {a["imdb_id"] for a in sync.compute_actions(simkl_items, stremio_items)}
        assert "tt9999999" not in action_ids

    def test_removed_stremio_item_re_added(self, simkl_items, stremio_items):
        stremio_items["tt2222222"] = {"imdb_id": "tt2222222", "watched": False, "removed": True, "raw": {"_id": "tt2222222"}}
        added_ids = {a["imdb_id"] for a in sync.compute_actions(simkl_items, stremio_items) if a["action"] == "add"}
        assert "tt2222222" in added_ids

    def test_empty_simkl_no_actions(self, stremio_items):
        assert sync.compute_actions({}, stremio_items) == []

    def test_empty_both_no_actions(self):
        assert sync.compute_actions({}, {}) == []


class TestNormalize:
    def test_simkl_movie(self):
        result = sync.simkl_normalize([SIMKL_RAW_MOVIE])
        assert result["tt5555555"]["title"] == "Raw Movie"
        assert result["tt5555555"]["watched"] is True

    def test_simkl_show(self):
        result = sync.simkl_normalize([SIMKL_RAW_SHOW])
        assert result["tt6666666"]["media_type"] == "series"
        assert result["tt6666666"]["watched"] is False

    def test_simkl_missing_imdb_skipped(self):
        raw = {"movie": {"title": "No IMDB", "ids": {"tmdb": 999}}, "simkl_status": "completed", "media_type": "movie"}
        assert len(sync.simkl_normalize([raw])) == 0

    def test_stremio_library(self):
        result = sync.stremio_normalize([STREMIO_RAW_ITEM])
        assert result["tt7777777"]["watched"] is True
        assert result["tt7777777"]["removed"] is False

    def test_stremio_non_imdb_skipped(self):
        assert len(sync.stremio_normalize([{**STREMIO_RAW_ITEM, "_id": "kitsu:12345"}])) == 0


class TestBuildLibraryItem:
    def test_watched_item(self):
        item = sync.build_library_item("tt1111111", "My Movie", "movie", True, "completed")
        assert item["state"]["timesWatched"] == 1
        assert item["state"]["flaggedWatched"] == 1
        assert item["state"]["lastWatched"] is not None

    def test_unwatched_item(self):
        item = sync.build_library_item("tt1111111", "My Movie", "movie", False, "plantowatch")
        assert item["state"]["timesWatched"] == 0
        assert item["state"]["lastWatched"] is None


# --- e2e tests ---

def _mock_simkl():
    responses.get(f"{sync.SIMKL_API_URL}/sync/all-items/movies/completed", json={"movies": [
        {"movie": {"title": "Inception", "ids": {"imdb": "tt1375666", "tmdb": 27205}}},
    ]})
    responses.get(f"{sync.SIMKL_API_URL}/sync/all-items/movies/watching", json={"movies": []})
    responses.get(f"{sync.SIMKL_API_URL}/sync/all-items/movies/plantowatch", json={"movies": [
        {"movie": {"title": "Dune Part Two", "ids": {"imdb": "tt15239678", "tmdb": 693134}}},
    ]})
    responses.get(f"{sync.SIMKL_API_URL}/sync/all-items/shows/completed", json={"shows": [
        {"show": {"title": "Breaking Bad", "ids": {"imdb": "tt0903747", "tmdb": 1396}}},
    ]})
    responses.get(f"{sync.SIMKL_API_URL}/sync/all-items/shows/watching", json={"shows": []})
    responses.get(f"{sync.SIMKL_API_URL}/sync/all-items/shows/plantowatch", json={"shows": []})
    for status in ["completed", "watching", "plantowatch"]:
        responses.get(f"{sync.SIMKL_API_URL}/sync/all-items/anime/{status}", json={"anime": []})


def _mock_cinemeta():
    responses.get("https://v3-cinemeta.strem.io/meta/series/tt0903747.json", json={"meta": {"videos": [
        {"id": "tt0903747:1:1", "season": 1, "episode": 1},
        {"id": "tt0903747:1:2", "season": 1, "episode": 2},
    ]}})
    responses.get("https://v3-cinemeta.strem.io/meta/series/tt1375666.json", json={"meta": {"videos": []}})
    responses.get("https://v3-cinemeta.strem.io/meta/series/tt15239678.json", json={"meta": {"videos": []}})


def _mock_stremio_get(items):
    responses.post(f"{sync.STREMIO_API_URL}/datastoreGet", json={"result": items})


def _mock_stremio_put():
    responses.post(f"{sync.STREMIO_API_URL}/datastorePut", json={"result": {"success": True}})


@responses.activate
def test_full_sync_adds_missing_items():
    _mock_simkl(); _mock_cinemeta(); _mock_stremio_get([]); _mock_stremio_put()
    result = sync.run_sync(dry_run=False)
    assert result["added"] == 3
    put_calls = [c for c in responses.calls if "datastorePut" in c.request.url]
    pushed_ids = {item["_id"] for item in json.loads(put_calls[0].request.body)["changes"]}
    assert pushed_ids == {"tt1375666", "tt15239678", "tt0903747"}


@responses.activate
def test_full_sync_skips_existing():
    _mock_simkl(); _mock_cinemeta(); _mock_stremio_put()
    _mock_stremio_get([{"_id": "tt1375666", "name": "Inception", "type": "movie", "removed": False, "state": {"timesWatched": 1, "flaggedWatched": 1}}])
    result = sync.run_sync(dry_run=False)
    assert result["added"] == 2
    assert result["skipped"] == 1


@responses.activate
def test_dry_run_makes_no_changes():
    _mock_simkl(); _mock_stremio_get([])
    result = sync.run_sync(dry_run=True)
    assert result["added"] == 0
    assert len([c for c in responses.calls if "datastorePut" in c.request.url]) == 0


@responses.activate
def test_idempotent_second_run():
    _mock_simkl(); _mock_cinemeta(); _mock_stremio_get([]); _mock_stremio_put()
    sync.run_sync(dry_run=False)

    responses.reset()
    _mock_simkl(); _mock_cinemeta()
    _mock_stremio_get([
        {"_id": "tt1375666", "name": "Inception", "type": "movie", "removed": False, "state": {"timesWatched": 1, "flaggedWatched": 1}},
        {"_id": "tt15239678", "name": "Dune Part Two", "type": "movie", "removed": False, "state": {"timesWatched": 0, "flaggedWatched": 0}},
        {"_id": "tt0903747", "name": "Breaking Bad", "type": "series", "removed": False, "state": {"timesWatched": 1, "flaggedWatched": 1, "watched": "tt0903747:1:2:2:eJxjYAAAAwAB"}},
    ])
    result = sync.run_sync(dry_run=False)
    assert result["added"] == 0
    assert len([c for c in responses.calls if "datastorePut" in c.request.url]) == 0
