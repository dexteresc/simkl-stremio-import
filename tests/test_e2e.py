import json

import responses

from stremio_simkl_sync import config
from stremio_simkl_sync.sync import run_sync


FAKE_AUTH_KEY = "test-stremio-auth-key"
FAKE_SIMKL_CLIENT_ID = "test-simkl-client-id"
FAKE_SIMKL_TOKEN = "test-simkl-token"


def setup_module():
    config.STREMIO_AUTH_KEY = FAKE_AUTH_KEY
    config.SIMKL_CLIENT_ID = FAKE_SIMKL_CLIENT_ID
    config.SIMKL_ACCESS_TOKEN = FAKE_SIMKL_TOKEN


def _mock_simkl_all_items():
    responses.get(
        f"{config.SIMKL_API_URL}/sync/all-items/movies/completed",
        json={"movies": [
            {
                "movie": {
                    "title": "Inception",
                    "ids": {"imdb": "tt1375666", "tmdb": 27205},
                },
            },
        ]},
    )
    responses.get(f"{config.SIMKL_API_URL}/sync/all-items/movies/watching", json={"movies": []})
    responses.get(
        f"{config.SIMKL_API_URL}/sync/all-items/movies/plantowatch",
        json={"movies": [
            {
                "movie": {
                    "title": "Dune Part Two",
                    "ids": {"imdb": "tt15239678", "tmdb": 693134},
                },
            },
        ]},
    )
    responses.get(
        f"{config.SIMKL_API_URL}/sync/all-items/shows/completed",
        json={"shows": [
            {
                "show": {
                    "title": "Breaking Bad",
                    "ids": {"imdb": "tt0903747", "tmdb": 1396},
                },
            },
        ]},
    )
    responses.get(f"{config.SIMKL_API_URL}/sync/all-items/shows/watching", json={"shows": []})
    responses.get(f"{config.SIMKL_API_URL}/sync/all-items/shows/plantowatch", json={"shows": []})
    for status in ["completed", "watching", "plantowatch"]:
        responses.get(f"{config.SIMKL_API_URL}/sync/all-items/anime/{status}", json={"anime": []})


def _mock_cinemeta():
    responses.add(
        responses.GET,
        "https://v3-cinemeta.strem.io/meta/series/tt0903747.json",
        json={"meta": {"videos": [
            {"id": "tt0903747:1:1", "season": 1, "episode": 1},
            {"id": "tt0903747:1:2", "season": 1, "episode": 2},
        ]}},
    )
    responses.add(
        responses.GET,
        "https://v3-cinemeta.strem.io/meta/series/tt1375666.json",
        json={"meta": {"videos": []}},
    )
    responses.add(
        responses.GET,
        "https://v3-cinemeta.strem.io/meta/series/tt15239678.json",
        json={"meta": {"videos": []}},
    )


def _mock_stremio_get(items):
    responses.post(
        f"{config.STREMIO_API_URL}/datastoreGet",
        json={"result": items},
    )


def _mock_stremio_put():
    responses.post(
        f"{config.STREMIO_API_URL}/datastorePut",
        json={"result": {"success": True}},
    )


@responses.activate
def test_full_sync_adds_missing_items():
    _mock_simkl_all_items()
    _mock_cinemeta()
    _mock_stremio_get([])  # empty stremio library
    _mock_stremio_put()

    result = run_sync(dry_run=False)

    assert result["added"] == 3  # inception, dune, breaking bad
    assert result["updated"] == 0

    put_calls = [c for c in responses.calls if "datastorePut" in c.request.url]
    assert len(put_calls) == 1
    body = json.loads(put_calls[0].request.body)
    pushed_ids = {item["_id"] for item in body["changes"]}
    assert pushed_ids == {"tt1375666", "tt15239678", "tt0903747"}


@responses.activate
def test_full_sync_skips_existing():
    _mock_simkl_all_items()
    _mock_cinemeta()
    _mock_stremio_get([
        {
            "_id": "tt1375666",
            "name": "Inception",
            "type": "movie",
            "removed": False,
            "state": {"timesWatched": 1, "flaggedWatched": 1},
        },
    ])
    _mock_stremio_put()

    result = run_sync(dry_run=False)

    assert result["added"] == 2  # dune + breaking bad
    assert result["skipped"] == 1  # inception


@responses.activate
def test_full_sync_updates_watched_state():
    _mock_simkl_all_items()
    _mock_cinemeta()
    _mock_stremio_get([
        {
            "_id": "tt1375666",
            "name": "Inception",
            "type": "movie",
            "removed": False,
            "poster": "https://example.com/inception.jpg",
            "_ctime": "2024-01-01T00:00:00Z",
            "state": {"timesWatched": 0, "flaggedWatched": 0},
        },
    ])
    _mock_stremio_put()

    result = run_sync(dry_run=False)

    assert result["updated"] == 1  # inception -> watched
    assert result["added"] == 2  # dune + breaking bad

    put_calls = [c for c in responses.calls if "datastorePut" in c.request.url]
    body = json.loads(put_calls[0].request.body)
    inception = next(i for i in body["changes"] if i["_id"] == "tt1375666")
    assert inception["state"]["flaggedWatched"] == 1
    assert inception["poster"] == "https://example.com/inception.jpg"
    assert inception["_ctime"] == "2024-01-01T00:00:00Z"


@responses.activate
def test_dry_run_makes_no_changes():
    _mock_simkl_all_items()
    _mock_stremio_get([])

    result = run_sync(dry_run=True)

    assert result["added"] == 0
    assert result["updated"] == 0
    put_calls = [c for c in responses.calls if "datastorePut" in c.request.url]
    assert len(put_calls) == 0


@responses.activate
def test_idempotent_second_run():
    _mock_simkl_all_items()
    _mock_cinemeta()
    _mock_stremio_get([])
    _mock_stremio_put()
    run_sync(dry_run=False)

    responses.reset()
    _mock_simkl_all_items()
    _mock_cinemeta()
    _mock_stremio_get([
        {
            "_id": "tt1375666",
            "name": "Inception",
            "type": "movie",
            "removed": False,
            "state": {"timesWatched": 1, "flaggedWatched": 1},
        },
        {
            "_id": "tt15239678",
            "name": "Dune Part Two",
            "type": "movie",
            "removed": False,
            "state": {"timesWatched": 0, "flaggedWatched": 0},
        },
        {
            "_id": "tt0903747",
            "name": "Breaking Bad",
            "type": "series",
            "removed": False,
            "state": {"timesWatched": 1, "flaggedWatched": 1, "watched": "tt0903747:1:2:2:eJxjYAAAAwAB"},
        },
    ])

    result = run_sync(dry_run=False)

    assert result["added"] == 0
    put_calls = [c for c in responses.calls if "datastorePut" in c.request.url]
    assert len(put_calls) == 0
