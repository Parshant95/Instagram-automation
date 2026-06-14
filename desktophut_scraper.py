"""
DesktopHut Live Wallpaper Scraper
Downloads exactly 3 video files per run from desktophut.com.
Skips files already downloaded. Run it daily via Task Scheduler.

Priority categories: Cars & Motorcycles, Anime (rotates between them)
Output: downloads/<category>/<filename>

Usage:
  python desktophut_scraper.py              # downloads 3 videos (Cars + Anime priority)
  python desktophut_scraper.py --cat anime  # 3 videos from anime only
  python desktophut_scraper.py --count 5   # change how many to download
"""

import argparse
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ── Constants ─────────────────────────────────────────────────────────────────

BASE_URL     = "https://www.desktophut.com"
DOWNLOAD_DIR = Path("downloads")
DELAY        = 1.5        # seconds between requests
CHUNK_SIZE   = 1024 * 512 # 512 KB

VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
}

# Priority order — script pulls from these first, rotates page by page
PRIORITY_CATEGORIES = [
    ("Cars & Motorcycles", "cars-motorcycles-live-wallpapers"),
    ("Anime",              "anime-live-wallpapers"),
]

ALL_CATEGORIES = [
    ("Animated Wallpapers",  "Animated-Wallpapers"),
    ("Anime",                "anime-live-wallpapers"),
    ("Abstract",             "abstract-live-wallpapers"),
    ("Animals",              "animals-live-wallpapers"),
    ("Fantasy / Sci-Fi",     "fantasy-sci-fi-live-wallpapers"),
    ("Games",                "games-live-wallpapers"),
    ("Landscape",            "landscape-live-wallpapers"),
    ("Movies & TV",          "movies-tv-live-wallpapers"),
    ("Pixel Art",            "pixel-art-live-wallpapers"),
    ("Cars & Motorcycles",   "cars-motorcycles-live-wallpapers"),
    ("Comics",               "comics-live-wallpapers"),
    ("3D Animation",         "3d-animation-live-wallpapers"),
    ("Tech",                 "tech-live-wallpapers"),
    ("Lofi",                 "Lofi"),
    ("Nature",               "nature-live-wallpapers"),
    ("Holidays",             "holidays-live-wallpapers"),
    ("People",               "people-live-wallpapers"),
    ("World",                "world-live-wallpapers"),
    ("Vehicles",             "vehicles-live-wallpapers"),
    ("Manga",                "manga-live-wallpapers"),
    ("Remastered 4K",        "remastered-4k-wallpapers"),
    ("Ultra HDR",            "ultra-hdr"),
    ("Black & White",        "black-and-white"),
    ("RGB",                  "rgb-live-wallpapers"),
    ("Halloween",            "halloween-live-wallpapers"),
    ("Cute",                 "cute-live-wallpapers"),
    ("Hello Kitty",          "hello-kitty-live-wallpapers"),
    ("Cool",                 "cool-live-wallpapers"),
    ("Black",                "black-live-wallpapers"),
    ("Pink",                 "pink-live-wallpapers"),
    ("Blue",                 "blue-live-wallpapers"),
    ("Red",                  "red-live-wallpapers"),
    ("Screensavers",         "screensavers"),
    ("Wallpaper Engine",     "wallpaper-engine-scene-wallpapers"),
    ("Stock Video Footage",  "stock-video-footage"),
    ("Preppy",               "Preppy-Wallpaper"),
    ("Other",                "other"),
]

# ── HTTP ──────────────────────────────────────────────────────────────────────

session = requests.Session()
session.headers.update(HEADERS)


def get(url: str, retries: int = 3):
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=20)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return None
        except requests.RequestException as e:
            print(f"  [!] Request error ({attempt+1}/{retries}): {e}")
        time.sleep(DELAY * (attempt + 1))
    return None


# ── Already-downloaded index ──────────────────────────────────────────────────

def already_downloaded() -> set[str]:
    """All filenames already saved under downloads/."""
    names = set()
    if DOWNLOAD_DIR.exists():
        for f in DOWNLOAD_DIR.rglob("*"):
            if f.is_file():
                names.add(f.name)
    return names


# ── Scraping helpers ──────────────────────────────────────────────────────────

def get_card_links(slug: str, page: int) -> list[str]:
    url = f"{BASE_URL}/category/{slug}?page={page}"
    r = get(url)
    if not r:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.match(r"^/[a-z0-9-]+_[A-Za-z0-9]+$", href):
            links.append(urljoin(BASE_URL, href))
    return list(dict.fromkeys(links))


def get_video_url(detail_url: str) -> tuple[str, str] | tuple[None, None]:
    """Visit a detail page, return (download_url, filename) for the video file."""
    r = get(detail_url)
    if not r:
        return None, None
    soup = BeautifulSoup(r.text, "html.parser")

    candidates = []
    for a in soup.find_all("a", href=True):
        if "/files/" in a["href"]:
            candidates.append(a["href"] if a["href"].startswith("http")
                              else urljoin(BASE_URL, a["href"]))
    for tag in soup.find_all(["video", "source"]):
        src = tag.get("src", "")
        if src and "/files/" in src:
            candidates.append(src if src.startswith("http") else urljoin(BASE_URL, src))

    for url in candidates:
        ext = Path(urlparse(url).path).suffix.lower()
        if ext in VIDEO_EXTS:
            return url, Path(urlparse(url).path).name

    return None, None


# ── Download ──────────────────────────────────────────────────────────────────

def download_file(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = session.get(url, stream=True, timeout=120)
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        written = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    written += len(chunk)
                    if total:
                        pct = written * 100 // total
                        size_mb = written / 1024 / 1024
                        print(f"\r  [DL] {dest.name}  {pct}%  ({size_mb:.1f} MB)", end="", flush=True)
        print()
        return True
    except Exception as e:
        print(f"\n  [!] Download failed: {e}")
        dest.unlink(missing_ok=True)
        return False


# ── Core: download N videos from a category list ─────────────────────────────

def download_videos(categories: list[tuple[str, str]], target: int = 3) -> int:
    """
    Download exactly `target` new video files across the given categories.
    Rotates through categories one video at a time (Cars → Anime → Cars → …)
    so the downloads folder stays balanced.
    Returns count of videos actually downloaded.
    """
    done = already_downloaded()
    downloaded = 0
    page_cursors = {slug: 1 for _, slug in categories}
    card_cursors: dict[str, list[str]] = {}
    exhausted = set()

    print(f"[*] Target: {target} new videos")
    print(f"[*] Already in library: {len(done)} files\n")

    # Round-robin across categories until we hit the target or run out
    while downloaded < target and len(exhausted) < len(categories):
        for name, slug in categories:
            if downloaded >= target:
                break
            if slug in exhausted:
                continue

            # Refill card list for this category if empty
            if slug not in card_cursors or not card_cursors[slug]:
                page = page_cursors[slug]
                print(f"[*] Fetching {name} — page {page}...")
                cards = get_card_links(slug, page)
                if not cards:
                    print(f"  [~] {name}: no more pages.")
                    exhausted.add(slug)
                    continue
                card_cursors[slug] = cards
                page_cursors[slug] += 1

            # Try next card in this category
            detail_url = card_cursors[slug].pop(0)
            time.sleep(DELAY)

            dl_url, filename = get_video_url(detail_url)
            if not dl_url or not filename:
                continue  # static image, skip silently

            if filename in done:
                print(f"  [=] Already have: {filename}")
                continue

            safe_cat = re.sub(r'[\\/:*?"<>|]', "_", name)
            dest = DOWNLOAD_DIR / safe_cat / filename

            print(f"  [{downloaded+1}/{target}] {filename}")
            if download_file(dl_url, dest):
                done.add(filename)
                downloaded += 1
            time.sleep(DELAY)

    return downloaded


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="DesktopHut — download N live wallpaper videos")
    parser.add_argument("--cat",   type=str, default="", help="Category filter (partial name match)")
    parser.add_argument("--count", type=int, default=3,  help="How many videos to download (default 3)")
    args = parser.parse_args()

    DOWNLOAD_DIR.mkdir(exist_ok=True)

    if args.cat:
        chosen = [
            (n, s) for n, s in ALL_CATEGORIES
            if args.cat.lower() in n.lower() or args.cat.lower() in s.lower()
        ]
        if not chosen:
            print(f"[!] No category matching '{args.cat}'.")
            sys.exit(1)
    else:
        chosen = PRIORITY_CATEGORIES  # Cars + Anime by default

    print(f"[*] Categories: {', '.join(n for n, _ in chosen)}")
    count = download_videos(chosen, target=args.count)
    print(f"\n[DONE] Downloaded {count} new video(s) -> {DOWNLOAD_DIR.resolve()}")


if __name__ == "__main__":
    main()
