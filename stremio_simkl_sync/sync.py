import time

from . import config, simkl_client, stremio_client


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
    raw_simkl = simkl_client.get_all_items()
    simkl_items = simkl_client.normalize_items(raw_simkl, tmdb_api_key=config.TMDB_API_KEY)
    print(f"  {len(simkl_items)} items from Simkl")

    print("Fetching Stremio library...")
    raw_stremio = stremio_client.get_library()
    stremio_items = stremio_client.normalize_library(raw_stremio)
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
        item = stremio_client.build_library_item(
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

    for i in range(0, len(changes), config.BATCH_SIZE):
        batch = changes[i : i + config.BATCH_SIZE]
        print(f"  Pushing batch {i // config.BATCH_SIZE + 1} ({len(batch)} items)...")
        stremio_client.put_library(batch)
        if i + config.BATCH_SIZE < len(changes):
            time.sleep(config.API_DELAY)

    print(f"\nDone: {len(adds)} added, {len(updates)} updated")
    return {"added": len(adds), "updated": len(updates), "skipped": skipped}
