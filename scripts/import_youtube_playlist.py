"""
Import a YouTube playlist (including Watch Later) into the knowledge base.

Usage:
    python3 scripts/import_youtube_playlist.py <playlist_url> [--cookies-from-browser BROWSER]

Examples:
    python3 scripts/import_youtube_playlist.py "https://www.youtube.com/playlist?list=WL"
    python3 scripts/import_youtube_playlist.py "https://www.youtube.com/playlist?list=WL" --cookies-from-browser chrome
"""

import sys
import argparse

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import yt_dlp
from src.pipeline.ingest import pipeline


def main():
    parser = argparse.ArgumentParser(description="Import a YouTube playlist into PKB")
    parser.add_argument("playlist_url", help="YouTube playlist URL")
    parser.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        default=None,
        help="Extract cookies from this browser (chrome, firefox, safari, edge)",
    )
    parser.add_argument(
        "--cookies-file",
        metavar="PATH",
        default=None,
        help="Path to a Netscape-format cookies.txt file exported from your browser",
    )
    args = parser.parse_args()

    playlist_url = args.playlist_url

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }
    if args.cookies_from_browser:
        ydl_opts["cookiesfrombrowser"] = (args.cookies_from_browser,)
    elif args.cookies_file:
        ydl_opts["cookiefile"] = args.cookies_file

    print(f"Fetching playlist metadata from: {playlist_url}")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(playlist_url, download=False)
    except Exception as e:
        print(f"Failed to fetch playlist: {e}", file=sys.stderr)
        sys.exit(1)

    entries = result.get("entries") or []
    total = len(entries)
    print(f"Found {total} videos\n")

    synced = skipped = errors = 0

    for i, entry in enumerate(entries, start=1):
        video_id = entry.get("id")
        title = entry.get("title") or video_id or "Unknown"

        if not video_id:
            print(f"({i}/{total}) [skip] missing video id")
            skipped += 1
            continue

        url = f"https://www.youtube.com/watch?v={video_id}"
        description_snippet = (entry.get("description") or "")[:200]
        text = f"Watch later: {url} — {title} {description_snippet}".strip()
        note_id = f"youtube_watchlater_{video_id}"

        try:
            res = pipeline.ingest(text=text, source="youtube_watch_later", note_id=note_id)
            status = res.get("status", "ok")
            if status == "skipped":
                print(f"({i}/{total}) {title} → skipped (unchanged)")
                skipped += 1
            else:
                print(f"({i}/{total}) {title} → ingested [{res.get('content_type', '?')}]")
                synced += 1
        except Exception as e:
            print(f"({i}/{total}) {title} → ERROR: {e}", file=sys.stderr)
            errors += 1

    print(f"\nDone — {synced} ingested, {skipped} skipped, {errors} errors")


if __name__ == "__main__":
    main()
