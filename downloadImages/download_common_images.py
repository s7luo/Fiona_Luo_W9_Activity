# Wikimedia Commons bulk image downloader
# Downloads images for multiple keyword searches and saves metadata as CSV.

import csv
import re
import time
from pathlib import Path

import requests
from PIL import Image

# -----------------------------
# SETTINGS — EDIT THESE
# -----------------------------

# Search terms. The script searches each one separately.
# The first term is also used to name the output folder.
KEYWORDS = [
    "disgust",
    "contempt",
    "disdain"
]

# Name used for the output folder.
# By default, this is the first keyword above.
DATASET_NAME = KEYWORDS[0]

# Commons categories that images may belong to.
# An image only needs to be in ONE of these categories.
INCLUDE_CATEGORIES = [
    "Disgust",
    "Emotions",
    "The_Expression_of_the_Emotions_in_Man_and_Animals",
    "The_Expression_of_Emotions_in_Man_and_Animals_in_the_National_Media_Museum",
    "Facial_expressions",
    "Contempt",
    "Emotions_in_art",
    "Mood",
    "Affect",
    "Temperament",
    "Personality",
    "Disposition",
    "Emotions",
    "Facial expressions",
    "People", 
    "Drawings",
    "Paintings", 
    "Art"
]

# Commons categories to exclude from the search.
EXCLUDE_CATEGORIES = [
    "Buildings",
    "Charts",
    "Graphs", "Illustrations", "Diagrams"

]

# How many images to download in total.
LIMIT = 100

# Download images at this maximum width, in pixels.
IMAGE_WIDTH = 1024

# Wait time between successful downloads, in seconds.
DOWNLOAD_DELAY = 1.5

# Words that cause an image to be skipped.
# The script checks the image title, description, and Commons categories.
# Keep this list specific; broad words can accidentally reject good images.
IGNORE_KEYWORDS = [
    "logo",
    "map",
    "diagram",
    "chart",
    "screenshot",
    "meme"
]

# Where downloaded images and metadata.csv will be saved.
# This creates the folder beside this Python script.
OUTPUT_ROOT = Path(__file__).resolve().parent / "wikimedia_images"

# -----------------------------
# DO NOT EDIT BELOW THIS LINE
# -----------------------------

API = "https://commons.wikimedia.org/w/api.php"

# Build the Commons category search filter.
include_filter = 'incategory:"' + "|".join(INCLUDE_CATEGORIES) + '"'

exclude_filter = " ".join(
    f'-incategory:"{category}"' for category in EXCLUDE_CATEGORIES
)

CATEGORY_FILTER = f"{include_filter} {exclude_filter}"

# Create the output directory.
OUTPUT_DIR = OUTPUT_ROOT / DATASET_NAME.replace(" ", "_")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print("Saving images to:", OUTPUT_DIR.resolve())

# Use a descriptive User-Agent.
# Replace the email address with your real email address.
session = requests.Session()
session.headers.update({
    "User-Agent": "GBDA414-classroom-dataset/1.0 (educational image research, d28han@uwaterloo.ca)"
})


def polite_get(url, params=None, max_retries=5):
    """Make a request, retrying politely if Wikimedia rate-limits us."""

    wait_time = 3

    for attempt in range(max_retries):
        response = session.get(url, params=params, timeout=30)

        if response.status_code in (403, 429):
            retry_after = response.headers.get("Retry-After")

            if retry_after:
                try:
                    wait = float(retry_after)
                except ValueError:
                    wait = wait_time
            else:
                wait = wait_time

            print(
                f"HTTP {response.status_code}. "
                f"Waiting {wait:.1f} seconds, then retrying..."
            )

            time.sleep(wait)
            wait_time = min(wait_time * 2, 60)
            continue

        response.raise_for_status()
        return response

    raise RuntimeError(
        "Wikimedia kept returning 403/429. "
        "Check that your User-Agent is descriptive and includes contact info."
    )


def clean_html(value):
    """Remove HTML tags and extra whitespace from Commons metadata."""

    if not value:
        return ""

    value = re.sub(r"<[^>]+>", "", value)
    return value.strip()


def contains_ignored_keyword(text):
    """Return True if any ignore keyword appears in the text."""

    text = (text or "").lower()
    return any(keyword.lower() in text for keyword in IGNORE_KEYWORDS)


def get_search_results():
    """Search Wikimedia Commons separately for each keyword."""

    for keyword in KEYWORDS:
        print(f"\nSearching Wikimedia Commons for: {keyword}")

        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"{keyword} filetype:bitmap {CATEGORY_FILTER}",
            "gsrnamespace": 6,  # File namespace
            "gsrlimit": 50,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime|size",
            "iiurlwidth": IMAGE_WIDTH,
            "origin": "*",
        }

        continue_token = {}

        while True:
            if continue_token:
                params.update(continue_token)

            data = polite_get(API, params).json()

            result_count = data.get("query", {}).get("searchinfo", {}).get("totalhits", 0)
            print(f"Commons search found {result_count} possible results for: {keyword}")

            pages = data.get("query", {}).get("pages", {})

            for page in pages.values():
                yield keyword, page

            continue_token = data.get("continue", {})

            if not continue_token:
                break


def main():
    rows = []
    downloaded = 0
    skipped_by_keyword = 0
    skipped_other = 0
    seen_titles = set()

    print(f"Downloading up to {LIMIT} images total.")
    print(f"Output folder: {OUTPUT_DIR}")
    print(f"Search terms: {', '.join(KEYWORDS)}")
    print(f"Include categories: {', '.join(INCLUDE_CATEGORIES)}")
    print(f"Exclude categories: {', '.join(EXCLUDE_CATEGORIES)}")
    print(f"Ignore keywords: {', '.join(IGNORE_KEYWORDS)}\n")

    for keyword, page in get_search_results():
        if downloaded >= LIMIT:
            break

        info = page.get("imageinfo", [{}])[0]
        raw_url = info.get("thumburl") or info.get("url")
        image_url = raw_url.split("?")[0] if raw_url else None

        if not image_url:
            skipped_other += 1
            continue

        title = page.get("title", "")

        # Avoid downloading the same Commons file twice
        # if it appears in more than one keyword search.
        if title in seen_titles:
            continue

        seen_titles.add(title)

        meta = info.get("extmetadata", {})

        clean_title = title.replace("File:", "")
        description = clean_html(meta.get("ImageDescription", {}).get("value", ""))
        categories = clean_html(meta.get("Categories", {}).get("value", ""))

        search_text = " ".join([
            clean_title,
            description,
            categories
        ])

        if contains_ignored_keyword(search_text):
            skipped_by_keyword += 1
            print(f"Skipped by ignore keyword: {clean_title}")
            continue

        safe_title = re.sub(r"[^\w\-_.]", "_", clean_title)[:100]
        extension = Path(image_url.split("?")[0]).suffix.lower() or ".jpg"
        filepath = OUTPUT_DIR / f"{downloaded + 1:03d}_{safe_title}{extension}"

        try:
            image_response = polite_get(image_url)
            filepath.write_bytes(image_response.content)

            # Confirm the downloaded file is actually a readable image.
            with Image.open(filepath) as image:
                image.verify()

            rows.append({
                "keyword": keyword,
                "file_title": clean_title,
                "image_path": str(filepath),
                "image_url": image_url,
                "description_url": info.get("descriptionurl", ""),
                "license": clean_html(meta.get("LicenseShortName", {}).get("value", "")),
                "artist": clean_html(meta.get("Artist", {}).get("value", "")),
                "credit": clean_html(meta.get("Credit", {}).get("value", "")),
                "description": description[:500],
                "categories": categories[:500],
                "width": info.get("width"),
                "height": info.get("height"),
            })

            downloaded += 1
            print(f"Downloaded {downloaded}/{LIMIT}: {clean_title}")

            time.sleep(DOWNLOAD_DELAY)

        except Exception as error:
            skipped_other += 1
            print(f"Skipped {clean_title}: {error}")
            time.sleep(2)

    metadata_path = OUTPUT_DIR / "metadata.csv"

    if rows:
        with open(metadata_path, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    print("\nFinished.")
    print(f"Downloaded: {downloaded}")
    print(f"Skipped by ignore keywords: {skipped_by_keyword}")
    print(f"Skipped for other reasons: {skipped_other}")
    print(f"Images saved to: {OUTPUT_DIR}")
    print(f"Metadata saved to: {metadata_path}")


if __name__ == "__main__":
    main()