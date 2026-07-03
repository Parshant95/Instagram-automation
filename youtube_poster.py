"""
YouTube Shorts Auto-Poster (one-shot mode — designed for GitHub Actions)
- Called once per scheduled run
- Uploads the next video (as a Short) that hasn't been posted to YouTube yet
- Shares the SAME content as the Instagram poster: it scans posts/pending/ and
  posts/done/, so videos get posted to YouTube whether or not Instagram has
  already moved them.
- Does NOT move files (Instagram owns the folder lifecycle); it only tracks
  what it has uploaded in posted_youtube.json.

Credentials (OAuth refresh-token flow, in order of priority):
  1. YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN env vars  <- GitHub Secrets
  2. youtube_config.json (local testing only — git-ignored)

Get a refresh token once by running:  python get_youtube_token.py
"""

import json
import gc
import os
import subprocess
import sys
import time
from pathlib import Path

from youtube_meta import generate_metadata

sys.stdout.reconfigure(encoding="utf-8")

CONFIG_FILE   = "youtube_config.json"
# Source videos from the local `downloads/` folder inside this project.
# Videos live in category subfolders (e.g. downloads/Anime, downloads/Cars).
SOURCE_DIRS   = [
    Path("downloads"),
]
POSTED_LOG    = Path("posted_youtube.json")

TEMP_DIR    = Path("temp")
MUSIC_DIR   = Path("music")
MUSIC_STATE = Path("music_state.json")

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv"}
MUSIC_EXTS = {".mp3", ".wav", ".aac", ".m4a"}

# Fit the full (uncropped) video into a vertical 1080x1920 Shorts frame,
# filling the top/bottom with a zoomed, blurred copy of itself.
SHORTS_VF = (
    "split[a][b];"
    "[b]scale=1080:1920:force_original_aspect_ratio=increase,"
    "crop=1080:1920,boxblur=20:2[bg];"
    "[a]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
    "[bg][fg]overlay=(W-w)/2:(H-h)/2"
)

# Upload-only scope — minimal permission needed to publish.
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"

# public / unlisted / private
PRIVACY_STATUS = os.environ.get("YT_PRIVACY", "public")


# ── Credentials ───────────────────────────────────────────────────────────────

def get_oauth_config() -> tuple[str, str, str]:
    cid   = os.environ.get("YT_CLIENT_ID")
    csec  = os.environ.get("YT_CLIENT_SECRET")
    rtok  = os.environ.get("YT_REFRESH_TOKEN")
    if cid and csec and rtok:
        return cid, csec, rtok
    if Path(CONFIG_FILE).exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg["client_id"], cfg["client_secret"], cfg["refresh_token"]
    raise RuntimeError(
        "No YouTube credentials found. Set YT_CLIENT_ID / YT_CLIENT_SECRET / "
        "YT_REFRESH_TOKEN env vars, or provide a local youtube_config.json. "
        "Run get_youtube_token.py to obtain a refresh token."
    )


# ── Posted-video log ──────────────────────────────────────────────────────────

def load_posted_log() -> set[str]:
    if POSTED_LOG.exists():
        return set(json.loads(POSTED_LOG.read_text(encoding="utf-8")))
    return set()


def mark_as_posted(filename: str):
    log = load_posted_log()
    log.add(filename)
    POSTED_LOG.write_text(json.dumps(sorted(log), indent=2), encoding="utf-8")


def already_posted(filename: str) -> bool:
    return filename in load_posted_log()


# ── Auth ──────────────────────────────────────────────────────────────────────

def build_service():
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    cid, csec, rtok = get_oauth_config()
    creds = Credentials(
        token=None,
        refresh_token=rtok,
        client_id=cid,
        client_secret=csec,
        token_uri=TOKEN_URI,
        scopes=SCOPES,
    )
    try:
        creds.refresh(Request())
    except RefreshError as e:
        raise RuntimeError(
            "YouTube OAuth refresh token is expired or revoked. "
            "Run `python get_youtube_token.py` again, then update "
            "`youtube_config.json` or the YT_REFRESH_TOKEN environment variable "
            "with the new refresh token."
        ) from e
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


# ── Queue ─────────────────────────────────────────────────────────────────────

def pending_videos() -> list[Path]:
    """Un-posted videos found anywhere under the source dirs — de-duped by name.

    Walks subfolders recursively so category folders (downloads/Anime, etc.)
    are picked up; the immediate parent folder name is used as the category.
    """
    seen: set[str] = set()
    by_category: dict[str, list[Path]] = {}
    for d in SOURCE_DIRS:
        if not d.exists():
            continue
        for f in sorted(d.rglob("*")):
            if not f.is_file() or f.suffix.lower() not in VIDEO_EXTS:
                continue
            if f.name in seen or already_posted(f.name):
                continue
            seen.add(f.name)
            by_category.setdefault(f.parent.name, []).append(f)

    # Round-robin across categories so runs alternate (Anime, Cars, Anime, ...).
    found: list[Path] = []
    queues = [by_category[c] for c in sorted(by_category)]
    while any(queues):
        for q in queues:
            if q:
                found.append(q.pop(0))
    return found


# ── FFmpeg + music ────────────────────────────────────────────────────────────

def get_ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


def get_music_files() -> list[Path]:
    if not MUSIC_DIR.exists():
        return []
    return sorted(f for f in MUSIC_DIR.iterdir() if f.suffix.lower() in MUSIC_EXTS)


def next_music_file() -> Path | None:
    files = get_music_files()
    if not files:
        return None
    state = json.loads(MUSIC_STATE.read_text(encoding="utf-8")) if MUSIC_STATE.exists() else {"last_index": -1}
    next_index = (state["last_index"] + 1) % len(files)
    MUSIC_STATE.write_text(json.dumps({"last_index": next_index}, indent=2), encoding="utf-8")
    chosen = files[next_index]
    print(f"[*] Music [{next_index + 1}/{len(files)}]: {chosen.name}")
    return chosen


def prepare_short(src: Path) -> Path:
    """Center-crop to vertical 1080x1920 and mix in rotating background music."""
    TEMP_DIR.mkdir(exist_ok=True)
    out = TEMP_DIR / (src.stem + "_short.mp4")
    if out.exists():
        out.unlink()

    music  = next_music_file()
    ffmpeg = get_ffmpeg()

    if music:
        print(f"[*] Cropping to 9:16 + mixing music: {src.name}")
        cmd = [
            ffmpeg, "-y",
            "-i", str(src),
            "-stream_loop", "-1",
            "-i", str(music),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-vf", SHORTS_VF,
            "-vcodec", "libx264",
            "-acodec", "aac",
            "-preset", "fast",
            "-crf", "23",
            "-shortest",
            "-movflags", "+faststart",
            str(out),
        ]
    else:
        print(f"[*] Cropping to 9:16 (no music available): {src.name}")
        cmd = [
            ffmpeg, "-y",
            "-i", str(src),
            "-vf", SHORTS_VF,
            "-vcodec", "libx264",
            "-acodec", "aac",
            "-preset", "fast",
            "-crf", "23",
            "-movflags", "+faststart",
            str(out),
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed:\n{result.stderr[-600:]}")

    print(f"[*] Ready: {out.name}")
    return out


# ── Upload ────────────────────────────────────────────────────────────────────

def upload_video(youtube, media_path: Path, original_name: str, category: str):
    from googleapiclient.http import MediaFileUpload

    meta = generate_metadata(original_name, category)

    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta["tags"],
            "categoryId": "24",  # Entertainment
        },
        "status": {
            "privacyStatus": PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False,
        },
    }

    print(f"[*] Uploading: {media_path.name}  (as {PRIVACY_STATUS})")
    media = None
    request = None
    try:
        media = MediaFileUpload(str(media_path), chunksize=-1, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"    ...{int(status.progress() * 100)}%")
    finally:
        request = None
        if media is not None:
            stream = getattr(media, "_fd", None)
            if stream is not None:
                stream.close()
        media = None
        gc.collect()

    video_id = response["id"]
    mark_as_posted(original_name)
    print(f"[+] Posted! https://www.youtube.com/shorts/{video_id}")


# ── Entry point ───────────────────────────────────────────────────────────────

def run():
    videos = pending_videos()
    if not videos:
        print("[~] No new videos to post to YouTube this slot.")
        sys.exit(0)

    print("[*] Authenticating with YouTube...")
    youtube = build_service()
    print("[*] Ready.\n")

    vid = videos[0]
    try:
        short = prepare_short(vid)
        upload_video(youtube, short, original_name=vid.name, category=vid.parent.name)
    except Exception as e:
        print(f"[!] Failed to upload: {e}")
        sys.exit(1)
    finally:
        for tmp in TEMP_DIR.glob(vid.stem + "_short.mp4"):
            for attempt in range(5):
                try:
                    tmp.unlink(missing_ok=True)
                    break
                except PermissionError:
                    if attempt == 4:
                        print(f"[!] Could not delete temp file because it is still in use: {tmp}")
                    else:
                        time.sleep(0.5)


if __name__ == "__main__":
    run()
