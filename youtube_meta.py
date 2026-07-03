"""
Auto-generates YouTube Shorts metadata (title, description, tags) from a filename.
Reuses the filename parsing + category hashtags from caption_generator.py.
Called by youtube_poster.py before uploading.
"""

from caption_generator import _filename_to_title, _detect_category, CATEGORY_TAGS

# YouTube hard limits
MAX_TITLE_LEN = 100
MAX_DESC_LEN  = 5000


def _tags_to_keywords(tags: list[str]) -> list[str]:
    """Strip the leading '#' so hashtags become plain YouTube keyword tags."""
    return [t.lstrip("#").replace(" ", "") for t in tags if t.strip()]


def generate_metadata(filename: str, category_folder: str) -> dict:
    """
    Returns {'title', 'description', 'tags'} ready for the YouTube API.
    A '#Shorts' tag is always added so vertical videos are treated as Shorts.
    """
    title = _filename_to_title(filename)
    cat   = _detect_category(category_folder)
    tags  = CATEGORY_TAGS.get(cat, CATEGORY_TAGS["default"])

    name_tag = "#" + title.replace(" ", "")
    hashtags = [name_tag, "#Shorts"] + tags

    yt_title = f"{title} #Shorts"[:MAX_TITLE_LEN]

    description = (
        f"{title} 🔥\n\n"
        f"{' '.join(hashtags)}"
    )[:MAX_DESC_LEN]

    keywords = _tags_to_keywords([name_tag, "#Shorts"] + tags)
    # YouTube allows max 500 chars total across tags; trim conservatively.
    trimmed, total = [], 0
    for kw in keywords:
        total += len(kw) + 1
        if total > 480:
            break
        trimmed.append(kw)

    return {"title": yt_title, "description": description, "tags": trimmed}


if __name__ == "__main__":
    for fname, folder in [
        ("Bgn64wPLkD-SasukeChillLiveWallpaper.mp4", "Anime"),
        ("Xk92mNpQ1R-LamborghiniNightDriveLiveWallpaper.mp4", "Cars"),
    ]:
        meta = generate_metadata(fname, folder)
        print(f"File : {fname}")
        print(f"Title: {meta['title']}")
        print(f"Desc :\n{meta['description']}")
        print(f"Tags : {meta['tags']}\n")
