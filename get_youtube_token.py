"""
One-time helper: obtain a YouTube OAuth refresh token for headless uploading.

Prerequisites:
  1. Google Cloud project with "YouTube Data API v3" enabled.
  2. OAuth client of type "Desktop app" -> download as client_secret.json
     into this folder.
  3. Add your channel's Google account as a Test User on the OAuth consent screen.

Run:
    python get_youtube_token.py

It opens a browser, you log in once, and it writes youtube_config.json with the
client_id / client_secret / refresh_token. Copy those three values into your
GitHub repo Secrets as YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN.
"""

import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET = "client_secret.json"
OUT = "youtube_config.json"


def main():
    if not Path(CLIENT_SECRET).exists():
        sys.exit(
            f"[!] {CLIENT_SECRET} not found.\n"
            "    Create an OAuth 'Desktop app' client in Google Cloud Console,\n"
            "    download it, and save it here as client_secret.json."
        )

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
    # access_type=offline + prompt=consent guarantees a refresh_token is returned.
    creds = flow.run_local_server(
        port=0, access_type="offline", prompt="consent"
    )

    if not creds.refresh_token:
        sys.exit("[!] No refresh token returned. Revoke prior access and retry.")

    out = {
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "refresh_token": creds.refresh_token,
    }
    Path(OUT).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[+] Wrote {OUT}")
    print("\nAdd these to GitHub repo Secrets:")
    print(f"  YT_CLIENT_ID     = {creds.client_id}")
    print(f"  YT_CLIENT_SECRET = {creds.client_secret}")
    print(f"  YT_REFRESH_TOKEN = {creds.refresh_token}")


if __name__ == "__main__":
    main()
