"""
Auto-generates Instagram captions + hashtags from a video filename.
Called by instagram_poster.py before posting.
"""

import re

# Per-category hashtag sets
CATEGORY_TAGS = {
    "cars": [
        "#cars", "#carporn", "#carlovers", "#supercar", "#exotic cars",
        "#automotive", "#carculture", "#carsofinstagram", "#sportscars",
        "#dreamcar", "#speed", "#racecar", "#luxurycars", "#carphoto",
        "#4k", "#livewallpaper", "#wallpaper",
    ],
    "anime": [
        "#anime", "#animewallpaper", "#animeart", "#animefan", "#animelife",
        "#otaku", "#mangaart", "#animelover", "#animeedits", "#animegirl",
        "#animescene", "#animecommunity", "#livewallpaper", "#4kwallpaper",
        "#wallpaper", "#aesthetic",
    ],
    "nature": [
        "#nature", "#naturewallpaper", "#landscape", "#naturelover",
        "#earthpix", "#scenic", "#outdoors", "#naturephotography",
        "#livewallpaper", "#4k", "#wallpaper", "#beautiful",
    ],
    "abstract": [
        "#abstract", "#abstractart", "#digitalart", "#abstractwallpaper",
        "#colorful", "#design", "#artoftheday", "#livewallpaper",
        "#4kwallpaper", "#wallpaper",
    ],
    "games": [
        "#gaming", "#gamer", "#gamingwallpaper", "#pcgaming", "#gamelife",
        "#videogames", "#gamers", "#livewallpaper", "#4k", "#wallpaper",
    ],
    "landscape": [
        "#landscape", "#scenery", "#earthpix", "#naturescenery",
        "#landscapewallpaper", "#livewallpaper", "#4kwallpaper", "#wallpaper",
    ],
    "default": [
        "#livewallpaper", "#wallpaper", "#4kwallpaper", "#desktop",
        "#wallpaperengine", "#aesthetic", "#satisfying", "#chill",
        "#vibes", "#screensaver",
    ],
}


def _detect_category(folder_name: str) -> str:
    folder = folder_name.lower()
    for key in CATEGORY_TAGS:
        if key in folder:
            return key
    return "default"


def _filename_to_title(filename: str) -> str:
    """
    Convert e.g. 'Bgn64wPLkD-SasukeChillLiveWallpaper.mp4'
    → 'Sasuke Chill Live Wallpaper'
    """
    stem = filename.rsplit(".", 1)[0]           # strip extension
    # Remove leading ID (10-char alphanum + dash)
    stem = re.sub(r"^[A-Za-z0-9]{10}-", "", stem)
    # Split CamelCase
    words = re.sub(r"([A-Z])", r" \1", stem).strip()
    # Remove trailing 'Live Wallpaper' for cleaner title (kept in hashtags)
    title = re.sub(r"\s*(Live\s*Wallpaper)\s*$", "", words, flags=re.IGNORECASE).strip()
    return title if title else words


def generate_caption(filename: str, category_folder: str) -> str:
    """
    Returns a ready-to-post Instagram caption with title + hashtags.
    """
    title = _filename_to_title(filename)
    cat   = _detect_category(category_folder)
    tags  = CATEGORY_TAGS.get(cat, CATEGORY_TAGS["default"])

    # Add name-based hashtag (e.g. #SasukeChill)
    name_tag = "#" + re.sub(r"\s+", "", title)
    all_tags  = [name_tag] + tags

    caption = f"{title} 🔥\n\n" + " ".join(all_tags)
    return caption


if __name__ == "__main__":
    # Quick test
    tests = [
        ("Bgn64wPLkD-SasukeChillLiveWallpaper.mp4",     "Anime"),
        ("Xk92mNpQ1R-LamborghiniNightDriveLiveWallpaper.mp4", "Cars & Motorcycles"),
        ("Ab12cdEf3G-MountainSunriseLiveWallpaper.mp4",  "Landscape"),
    ]
    for fname, folder in tests:
        print(f"File   : {fname}")
        print(f"Folder : {folder}")
        print(f"Caption:\n{generate_caption(fname, folder)}")
        print()
