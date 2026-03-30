import os
from dotenv import load_dotenv

load_dotenv()

STREMIO_AUTH_KEY = os.getenv("STREMIO_AUTH_KEY", "")
SIMKL_CLIENT_ID = os.getenv("SIMKL_CLIENT_ID", "")
SIMKL_ACCESS_TOKEN = os.getenv("SIMKL_ACCESS_TOKEN", "")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")

STREMIO_API_URL = "https://api.strem.io/api"
SIMKL_API_URL = "https://api.simkl.com"

BATCH_SIZE = 50
API_DELAY = 1.0
