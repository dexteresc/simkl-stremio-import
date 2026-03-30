import argparse
import getpass
import sys

from . import config, simkl_client, stremio_client
from .sync import run_sync


def main():
    parser = argparse.ArgumentParser(description="Sync Simkl library to Stremio")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    parser.add_argument("--simkl-auth", action="store_true", help="Run Simkl PIN authentication")
    parser.add_argument("--stremio-login", action="store_true", help="Login to Stremio with email/password")
    args = parser.parse_args()

    if args.stremio_login:
        email = input("Stremio email: ")
        password = getpass.getpass("Stremio password: ")
        auth_key = stremio_client.login(email, password)
        config.STREMIO_AUTH_KEY = auth_key
        if not args.simkl_auth and not args.dry_run:
            return

    if args.simkl_auth:
        if not config.SIMKL_CLIENT_ID:
            print("Error: SIMKL_CLIENT_ID not set in .env")
            sys.exit(1)
        simkl_client.authenticate_pin()
        if not args.dry_run:
            return

    if not config.STREMIO_AUTH_KEY:
        config.STREMIO_AUTH_KEY = stremio_client.load_auth_key() or ""
    if not config.SIMKL_ACCESS_TOKEN:
        config.SIMKL_ACCESS_TOKEN = simkl_client.load_token() or ""

    missing = []
    if not config.STREMIO_AUTH_KEY:
        missing.append("STREMIO_AUTH_KEY (run --stremio-login or set in .env)")
    if not config.SIMKL_CLIENT_ID:
        missing.append("SIMKL_CLIENT_ID")
    if not config.SIMKL_ACCESS_TOKEN:
        missing.append("SIMKL_ACCESS_TOKEN (run --simkl-auth or set in .env)")
    if missing:
        print(f"Error: missing config:\n  " + "\n  ".join(missing))
        sys.exit(1)

    run_sync(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
