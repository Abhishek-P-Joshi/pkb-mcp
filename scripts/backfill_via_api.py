"""
Backfill YouTube metadata for all existing videos using the YouTube Data API v3.

Much faster than the yt-dlp backfill (0.1s between requests, no scraping).
Uses 1 API unit per video — well within the 10,000 units/day free quota.

Safe to interrupt and re-run — already-enriched rows are skipped.

Usage:
    python3 scripts/backfill_via_api.py
"""

import sys
import time
import sqlite3
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import config
from src.connectors.youtube_api import get_authenticated_service, get_video_metadata


def build_enriched_suffix(meta: dict) -> str:
    suffix = ""
    if meta.get("title"):
        suffix += f"\n\nTitle: {meta['title']}"
    if meta.get("channel"):
        suffix += f"\nChannel: {meta['channel']}"
    if meta.get("description"):
        suffix += f"\nDescription: {meta['description']}"
    if meta.get("tags"):
        suffix += f"\nTags: {meta['tags']}"
    if meta.get("categories"):
        suffix += f"\nCategories: {meta['categories']}"
    if meta.get("language"):
        suffix += f"\nLanguage: {meta['language']}"
    if meta.get("uploaded_at"):
        suffix += f"\nUploaded: {meta['uploaded_at']}"
    if meta.get("duration_string"):
        suffix += f"\nDuration: {meta['duration_string']}"
    return suffix


def main():
    print("Authenticating with YouTube API...")
    service = get_authenticated_service()
    print("Auth OK\n")

    conn = sqlite3.connect(config.sqlite_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT id, url, title, raw_text
        FROM notes
        WHERE content_type = 'video'
          AND url LIKE '%youtube%'
          AND (channel IS NULL OR channel = '' OR duration_seconds IS NULL)
        ORDER BY created_at DESC
    """).fetchall()
    rows = [dict(r) for r in rows]
    total = len(rows)

    print(f"Found {total} videos to enrich\n")

    updated = skipped = errors = 0
    start_time = time.time()

    for i, row in enumerate(rows, start=1):
        note_id = row["id"]
        url     = row["url"]
        title   = (row["title"] or "")[:50]

        # Extract video_id from URL
        parsed   = urlparse(url)
        video_id = parse_qs(parsed.query).get("v", [None])[0]

        if not video_id:
            print(f"({i}/{total}) SKIP — could not extract video_id from: {url}", file=sys.stderr)
            skipped += 1
            continue

        try:
            meta = get_video_metadata(service, video_id)

            # Rebuild raw_text with enriched suffix
            existing_raw = row["raw_text"] or ""
            base_text    = existing_raw.split("\n\nTitle:")[0]
            new_raw_text = base_text + build_enriched_suffix(meta)

            conn.execute("""
                UPDATE notes SET
                    uploaded_at      = ?,
                    channel          = ?,
                    channel_id       = ?,
                    duration_seconds = ?,
                    duration_string  = ?,
                    view_count       = ?,
                    like_count       = ?,
                    categories       = ?,
                    language         = ?,
                    thumbnail_url    = ?,
                    raw_text         = ?,
                    updated_at       = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                meta.get("uploaded_at"),
                meta.get("channel"),
                meta.get("channel_id"),
                meta.get("duration_seconds"),
                meta.get("duration_string"),
                meta.get("view_count"),
                meta.get("like_count"),
                meta.get("categories"),
                meta.get("language"),
                meta.get("thumbnail_url"),
                new_raw_text,
                note_id,
            ))
            conn.commit()
            updated += 1

            if i % 10 == 0 or i == 1:
                channel  = meta.get("channel", "?")
                duration = meta.get("duration_string", "?")
                uploaded = meta.get("uploaded_at", "?")
                print(f"({i}/{total}) {title} | {channel} | {duration} | {uploaded}")

        except Exception as e:
            print(f"({i}/{total}) ERROR for {title}: {e}", file=sys.stderr)
            errors += 1

        # Progress + ETA every 50 videos
        if i % 50 == 0:
            elapsed     = time.time() - start_time
            avg_time    = elapsed / i
            eta_minutes = (total - i) * avg_time / 60
            print(
                f"--- Progress: {i}/{total} | {errors} errors | "
                f"~{eta_minutes:.1f}min remaining ---"
            )

        time.sleep(0.1)

    conn.close()

    elapsed_minutes = (time.time() - start_time) / 60
    print("\nBackfill complete!")
    print(f"  Updated: {updated}")
    print(f"  Skipped: {skipped} (no video_id in URL)")
    print(f"  Errors:  {errors}")
    print(f"  Time:    {elapsed_minutes:.1f} minutes")
    print(f"  API units used: ~{updated} of 10,000 daily quota")


if __name__ == "__main__":
    main()
