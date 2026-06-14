"""
Quick test — posts one video immediately with music + caption.
Skips any video that has already been posted.
Run: python test_post.py
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from caption_generator import generate_caption
from instagram_poster import (
    prepare_video, get_music_files, login,
    already_posted, mark_as_posted
)

CONFIG_FILE  = "config.json"
DOWNLOAD_DIR = Path("downloads")
VIDEO_EXTS   = {".mp4", ".mov", ".webm", ".mkv"}


def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def find_next_video() -> tuple[Path, str] | tuple[None, None]:
    """Return the first video in downloads/ that hasn't been posted yet."""
    for cat_dir in sorted(DOWNLOAD_DIR.iterdir()):
        if cat_dir.is_dir():
            for f in sorted(cat_dir.iterdir()):
                if f.suffix.lower() in VIDEO_EXTS and "_ready" not in f.stem and "_ig" not in f.stem:
                    if already_posted(f.name):
                        print(f"[=] Already posted, skipping: {f.name}")
                        continue
                    return f, cat_dir.name
    return None, None


def main():
    cfg = load_config()

    video, category = find_next_video()
    if not video:
        print("[!] No new videos to post — all videos in downloads/ have already been posted.")
        print("    Run the scraper to download more: python desktophut_scraper.py")
        return

    caption = generate_caption(video.name, category)

    print(f"[*] Video   : {video.name}")
    print(f"[*] Category: {category}")
    print(f"[*] Caption :\n{caption}\n")

    music_files = get_music_files()
    if music_files:
        print(f"[*] Music library: {len(music_files)} file(s)")
    else:
        print("[!] No music files in music/ — posting without music")

    ready = prepare_video(video)

    print("\n[*] Logging into Instagram...")
    cl = login(cfg)

    print("\n[*] Uploading...")
    media = cl.clip_upload(ready, caption=caption)
    ready.unlink(missing_ok=True)

    mark_as_posted(video.name)
    print(f"\n[OK] Posted!")
    print(f"     URL: https://www.instagram.com/p/{media.code}/")


if __name__ == "__main__":
    main()
