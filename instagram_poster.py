"""
Instagram Auto-Poster (one-shot mode — designed for GitHub Actions)
- Called once per scheduled run (12:00 PM and 8:00 PM IST via GitHub Actions cron)
- Posts the next queued video from posts/pending/
- Moves it to posts/done/ and logs it to posted_videos.json
- Saves updated session.json so login persists across runs

Credentials (in order of priority):
  1. IG_USERNAME / IG_PASSWORD environment variables  <- GitHub Actions Secrets
  2. config.json (for local testing only — never commit this file)

Folder flow:
  posts/pending/  <- commit your .mp4 files here
  posts/done/     <- moved here automatically after posting
  music/          <- optional .mp3/.wav files for background music
"""

import json
import os
import shutil
import socket
import sys
import time
from pathlib import Path

from caption_generator import generate_caption

sys.stdout.reconfigure(encoding="utf-8")

CONFIG_FILE = "config.json"
PENDING_DIR = Path("posts/pending")
DOWNLOADS_DIR = Path("downloads")
DONE_DIR    = Path("posts/done")
MUSIC_DIR   = Path("music")
MUSIC_STATE = Path("music_state.json")
TEMP_DIR    = Path("temp")
POSTED_LOG  = Path("posted_videos.json")

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv"}
MUSIC_EXTS = {".mp3", ".wav", ".aac", ".m4a"}


# ── Network readiness ───────────────────────────────────────────────────────

def wait_for_network(host: str = "i.instagram.com", retries: int = 10, delay: int = 30) -> bool:
    """Block until DNS resolves for `host`, or give up after `retries` attempts.

    Guards against transient DNS/connectivity failures (e.g. when a scheduled
    run fires before the network is up after boot/wake).
    """
    for attempt in range(1, retries + 1):
        try:
            socket.getaddrinfo(host, 443)
            return True
        except socket.gaierror:
            print(f"[!] Network not ready (attempt {attempt}/{retries}), "
                  f"retrying in {delay}s...")
            time.sleep(delay)
    return False


# ── Credentials ───────────────────────────────────────────────────────────────

def get_credentials() -> tuple[str | None, str | None]:
    username = os.environ.get("IG_USERNAME")
    password = os.environ.get("IG_PASSWORD")
    if username and password:
        return username, password
    if Path(CONFIG_FILE).exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg["username"], cfg["password"]
    return None, None


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


# ── FFmpeg ────────────────────────────────────────────────────────────────────

def get_ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


# ── Login ─────────────────────────────────────────────────────────────────────

def login(username: str | None, password: str | None):
    from instagrapi import Client
    cl = Client()
    session_file = Path("session.json")

    # Keep the same device fingerprint across re-logins. Inventing a new
    # device/UUID on every fresh login is what makes Instagram fire a
    # "new device" challenge_required checkpoint.
    device_settings = None

    if session_file.exists():
        try:
            cl.load_settings(session_file)
            device_settings = cl.get_settings()
            # A session built via login_by_sessionid already carries valid
            # authorization_data — do NOT call cl.login(user, pass) here, as
            # that hits the login API and re-triggers the challenge checkpoint.
            # Validate with a lightweight authenticated request instead.
            cl.account_info()
            cl.dump_settings(session_file)
            print("[*] Logged in via saved session.")
            return cl
        except Exception as e:
            # Do NOT delete session.json here. A transient 403/rate-limit
            # would otherwise destroy a perfectly good session and force a
            # checkpoint-triggering fresh login. Keep the file; just fall
            # through and let the operator decide.
            print(f"[!] Saved session check failed ({e}).")
            if not username or not password:
                raise RuntimeError(
                    "Saved session is not usable right now and no "
                    "username/password is set for fallback. This is usually a "
                    "temporary rate-limit/checkpoint — wait a few hours and "
                    "retry, or regenerate session.json with make_session.py. "
                    "session.json was left intact."
                ) from e
            print("[!] Attempting fresh login...")
            cl = Client()
            if device_settings:
                # Reuse the old device/uuids, drop only the dead auth tokens.
                cl.set_settings(device_settings)
                cl.set_uuids(device_settings.get("uuids", {}))

    if not username or not password:
        raise RuntimeError(
            "No usable saved session found. Set IG_USERNAME and IG_PASSWORD env vars, "
            "or provide a local config.json for fallback login."
        )

    try:
        cl.login(username, password)
    except Exception as e:
        raise RuntimeError(
            f"Fresh login failed: {e}\n"
            "If this is a challenge_required/checkpoint, open the Instagram "
            "app on a trusted device, confirm the login, then re-run locally "
            "from your home IP to regenerate session.json."
        ) from e
    cl.dump_settings(session_file)
    print("[*] Logged in and session saved.")
    return cl


# ── Music rotation ────────────────────────────────────────────────────────────

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


# ── Video processing ──────────────────────────────────────────────────────────

def prepare_video(src: Path) -> Path:
    import subprocess
    TEMP_DIR.mkdir(exist_ok=True)
    out = TEMP_DIR / (src.stem + "_ready.mp4")
    if out.exists():
        out.unlink()

    music  = next_music_file()
    ffmpeg = get_ffmpeg()

    if music:
        print(f"[*] Converting + mixing music: {src.name}")
        cmd = [
            ffmpeg, "-y",
            "-i", str(src),
            "-stream_loop", "-1",
            "-i", str(music),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-vcodec", "libx264",
            "-acodec", "aac",
            "-vf", "scale=1080:-2",
            "-preset", "fast",
            "-crf", "23",
            "-shortest",
            "-movflags", "+faststart",
            str(out)
        ]
    else:
        print(f"[*] Converting to H.264 (no music): {src.name}")
        cmd = [
            ffmpeg, "-y",
            "-i", str(src),
            "-vcodec", "libx264",
            "-acodec", "aac",
            "-vf", "scale=1080:-2",
            "-preset", "fast",
            "-crf", "23",
            "-movflags", "+faststart",
            str(out)
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed:\n{result.stderr[-600:]}")

    print(f"[*] Ready: {out.name}")
    return out


def generate_thumbnail(video_path: Path) -> Path:
    import subprocess

    TEMP_DIR.mkdir(exist_ok=True)
    thumb = TEMP_DIR / f"{video_path.stem}.jpg"
    if thumb.exists():
        thumb.unlink()

    ffmpeg = get_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-ss", "00:00:01",
        "-i", str(video_path),
        "-frames:v", "1",
        "-vf", "scale=1080:-2",
        str(thumb),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not thumb.exists():
        raise RuntimeError(f"Thumbnail generation failed:\n{result.stderr[-600:]}")

    print(f"[*] Thumbnail ready: {thumb.name}")
    return thumb


# ── Queue ─────────────────────────────────────────────────────────────────────

def pending_videos() -> list[Path]:
    """Collect un-posted videos from posts/pending/ and downloads/<category>/."""
    candidates: list[Path] = []

    if PENDING_DIR.exists():
        candidates.extend(
            f for f in PENDING_DIR.iterdir() if f.suffix.lower() in VIDEO_EXTS
        )

    if DOWNLOADS_DIR.exists():
        candidates.extend(
            f for f in DOWNLOADS_DIR.rglob("*")
            # skip the "*_ig.mp4" intermediates produced by the scraper
            if f.suffix.lower() in VIDEO_EXTS and not f.stem.endswith("_ig")
        )

    return sorted(
        (f for f in candidates if not already_posted(f.name)),
        key=lambda f: f.name,
    )


def move_to_done(media_path: Path):
    DONE_DIR.mkdir(parents=True, exist_ok=True)
    dest = DONE_DIR / media_path.name
    if dest.exists():
        dest = DONE_DIR / f"{media_path.stem}_{int(time.time())}{media_path.suffix}"
    shutil.move(str(media_path), dest)


# ── Post ──────────────────────────────────────────────────────────────────────

def post_video(cl, media_path: Path):
    category = media_path.parent.name if media_path.parent != PENDING_DIR else "pending"
    caption  = generate_caption(media_path.name, category)
    ready    = prepare_video(media_path)
    thumb    = generate_thumbnail(ready)
    try:
        print(f"[*] Uploading: {media_path.name}")
        media = cl.clip_upload(ready, caption=caption, thumbnail=thumb)
        mark_as_posted(media_path.name)
        print(f"[+] Posted! https://www.instagram.com/p/{media.code}/")
    finally:
        ready.unlink(missing_ok=True)
        thumb.unlink(missing_ok=True)


# ── Entry point ───────────────────────────────────────────────────────────────

def run():
    PENDING_DIR.mkdir(parents=True, exist_ok=True)

    videos = pending_videos()
    if not videos:
        print("[~] No videos in posts/pending/ — nothing to post this slot.")
        sys.exit(0)

    if not wait_for_network():
        print("[!] No network after retries — aborting this run.")
        sys.exit(1)

    print("[*] Logging into Instagram...")
    username, password = get_credentials()
    cl = login(username, password)
    print("[*] Ready.\n")

    vid = videos[0]
    try:
        post_video(cl, vid)
        move_to_done(vid)
    except Exception as e:
        print(f"[!] Failed to post: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run()
