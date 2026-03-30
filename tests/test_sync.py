from stremio_simkl_sync.sync import compute_actions
from stremio_simkl_sync.simkl_client import normalize_items
from stremio_simkl_sync.stremio_client import normalize_library, build_library_item
from tests.conftest import SIMKL_RAW_MOVIE, SIMKL_RAW_SHOW, STREMIO_RAW_ITEM


class TestComputeActions:
    def test_new_item_added(self, simkl_items, stremio_items):
        actions = compute_actions(simkl_items, stremio_items)
        added_ids = {a["imdb_id"] for a in actions if a["action"] == "add"}
        assert "tt2222222" in added_ids
        assert "tt3333333" in added_ids

    def test_already_synced_skipped(self, simkl_items, stremio_items):
        actions = compute_actions(simkl_items, stremio_items)
        action_ids = {a["imdb_id"] for a in actions}
        assert "tt1234567" not in action_ids

    def test_watched_state_update(self, simkl_items, stremio_items):
        stremio_items["tt2222222"] = {
            "imdb_id": "tt2222222",
            "watched": False,
            "removed": False,
            "raw": {"_id": "tt2222222", "name": "Plan To Watch Movie", "_ctime": "2024-01-01T00:00:00Z"},
        }
        simkl_items["tt2222222"]["watched"] = True
        simkl_items["tt2222222"]["status"] = "completed"

        actions = compute_actions(simkl_items, stremio_items)
        updates = [a for a in actions if a["imdb_id"] == "tt2222222"]
        assert len(updates) == 1
        assert updates[0]["action"] == "update"

    def test_stremio_only_ignored(self, simkl_items, stremio_items):
        actions = compute_actions(simkl_items, stremio_items)
        action_ids = {a["imdb_id"] for a in actions}
        assert "tt9999999" not in action_ids

    def test_removed_stremio_item_re_added(self, simkl_items, stremio_items):
        stremio_items["tt2222222"] = {
            "imdb_id": "tt2222222",
            "watched": False,
            "removed": True,
            "raw": {"_id": "tt2222222"},
        }
        actions = compute_actions(simkl_items, stremio_items)
        added_ids = {a["imdb_id"] for a in actions if a["action"] == "add"}
        assert "tt2222222" in added_ids

    def test_empty_simkl_no_actions(self, stremio_items):
        assert compute_actions({}, stremio_items) == []

    def test_empty_both_no_actions(self):
        assert compute_actions({}, {}) == []


class TestNormalizeSimkl:
    def test_movie_normalization(self):
        result = normalize_items([SIMKL_RAW_MOVIE])
        assert "tt5555555" in result
        item = result["tt5555555"]
        assert item["title"] == "Raw Movie"
        assert item["media_type"] == "movie"
        assert item["watched"] is True

    def test_show_normalization(self):
        result = normalize_items([SIMKL_RAW_SHOW])
        assert "tt6666666" in result
        item = result["tt6666666"]
        assert item["title"] == "Raw Show"
        assert item["media_type"] == "series"
        assert item["watched"] is False

    def test_missing_imdb_skipped(self):
        raw = {"movie": {"title": "No IMDB", "ids": {"tmdb": 999}}, "simkl_status": "completed", "media_type": "movie"}
        result = normalize_items([raw])
        assert len(result) == 0


class TestNormalizeStremio:
    def test_library_normalization(self):
        result = normalize_library([STREMIO_RAW_ITEM])
        assert "tt7777777" in result
        item = result["tt7777777"]
        assert item["watched"] is True
        assert item["removed"] is False

    def test_non_imdb_skipped(self):
        raw = {**STREMIO_RAW_ITEM, "_id": "kitsu:12345"}
        result = normalize_library([raw])
        assert len(result) == 0


class TestBuildLibraryItem:
    def test_watched_item(self):
        item = build_library_item("tt1111111", "My Movie", "movie", True, "completed")
        assert item["_id"] == "tt1111111"
        assert item["name"] == "My Movie"
        assert item["type"] == "movie"
        assert item["removed"] is False
        assert item["state"]["timesWatched"] == 1
        assert item["state"]["flaggedWatched"] == 1
        assert item["state"]["lastWatched"] is not None

    def test_unwatched_item(self):
        item = build_library_item("tt1111111", "My Movie", "movie", False, "plantowatch")
        assert item["state"]["timesWatched"] == 0
        assert item["state"]["flaggedWatched"] == 0
        assert item["state"]["lastWatched"] is None
