# simkl-stremio-import

Import your Simkl watch history into Stremio's library with per-episode tracking.

SyncriBullet handles Stremio → Simkl. This handles the reverse.

## What it does

- Reads your Simkl library (movies, series, anime)
- Pushes items into Stremio's cloud library via the datastore API
- Marks individual episodes as watched using Stremio's bitfield format
- Aggregates multi-season anime that Simkl tracks as separate entries

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in .env with your credentials
```

### Getting credentials

- **STREMIO_AUTH_KEY** — open [web.stremio.com](https://web.stremio.com), run in console: `JSON.parse(localStorage.getItem("profile")).auth.key`
- **SIMKL_CLIENT_ID** — register at [simkl.com/settings/developer](https://simkl.com/settings/developer/)
- **SIMKL_ACCESS_TOKEN** — run `python -m stremio_simkl_sync --simkl-auth`
- **TMDB_API_KEY** *(optional)* — for resolving anime seasons without IMDB IDs

## Usage

```bash
# preview changes
python -m stremio_simkl_sync --dry-run

# run sync
python -m stremio_simkl_sync
```
