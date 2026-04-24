"""
Backfill YouTube metadata for all existing videos in the knowledge base.

Fetches full metadata (channel, duration, views, categories, language,
thumbnail, upload date) for every YouTube video and updates the database.

Safe to interrupt and re-run — already-enriched rows are skipped.

Usage:
    python3 scripts/backfill_metadata.py
"""

import sys
import time
import sqlite3

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from src.config import config
from src.pipeline.enricher import URLEnricher


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
    enricher = URLEnricher()
    conn = sqlite3.connect(config.sqlite_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT id, url, title, raw_text,
               channel, duration_seconds, view_count
        FROM notes
        WHERE content_type = 'video'
          AND url LIKE '%youtube%'
        ORDER BY created_at DESC
    """).fetchall()
    rows = [dict(r) for r in rows]
    total = len(rows)

    print(f"Found {total} YouTube videos to process\n")

    updated = skipped = errors = 0
    start_time = time.time()
    video_times = []

    for i, row in enumerate(rows, start=1):
        note_id = row["id"]
        url = row["url"]
        title = (row["title"] or "")[:50]

        # Skip if already fully enriched
        if row["channel"] and row["duration_seconds"] and row["view_count"]:
            print(f"({i}/{total}) skipping {title} (already enriched)")
            skipped += 1
            continue

        video_start = time.time()
        try:
            meta = enricher.enrich(url)

            # Build updated raw_text — replace old suffix or append new one
            existing_raw = row["raw_text"] or ""
            # Strip any old enriched suffix (everything from "\n\nTitle:" onward)
            base_text = existing_raw.split("\n\nTitle:")[0].split("\n\nChannel:")[0]
            new_suffix = build_enriched_suffix(meta)
            new_raw_text = base_text + new_suffix

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

            channel = meta.get("channel", "?")
            duration = meta.get("duration_string", "?")
            uploaded = meta.get("uploaded_at", "?")
            if i % 10 == 0 or i == 1:
                print(f"({i}/{total}) {title} | {channel} | {duration} | {uploaded}")

            updated += 1
            video_times.append(time.time() - video_start)

        except Exception as e:
            print(f"({i}/{total}) ERROR for {title}: {e}", file=sys.stderr)
            errors += 1

        # Progress + ETA every 50 videos
        if i % 50 == 0:
            elapsed = time.time() - start_time
            avg_time = elapsed / i
            remaining = (total - i) * avg_time
            eta_minutes = remaining / 60
            done = updated + skipped
            print(
                f"--- Progress: {done}/{total} | {errors} errors | "
                f"~{eta_minutes:.1f}min remaining ---"
            )

        time.sleep(0.3)

    conn.close()

    elapsed_minutes = (time.time() - start_time) / 60
    print("\nBackfill complete!")
    print(f"  Updated: {updated}")
    print(f"  Skipped: {skipped} (already had metadata)")
    print(f"  Errors:  {errors}")
    print(f"  Time:    {elapsed_minutes:.1f} minutes")


if __name__ == "__main__":
    main()
