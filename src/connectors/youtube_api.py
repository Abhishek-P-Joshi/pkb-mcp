"""
YouTube Data API v3 connector.

Replaces yt-dlp for playlist sync and metadata fetching.
Uses OAuth2 so private playlists (Watch Later, Liked Videos) are accessible.

Setup:
  1. Go to https://console.cloud.google.com/
  2. Create a project → Enable YouTube Data API v3
  3. Create OAuth2 credentials (Desktop app) → Download as JSON
  4. Save the file as config/youtube_oauth_client.json
  5. Run any sync function — a browser window will open for auth on first run
"""

import re
import sys
import json
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

_PROJECT_ROOT = Path(__file__).parent.parent.parent
CLIENT_SECRETS_FILE = str(_PROJECT_ROOT / "config" / "youtube_oauth_client.json")
TOKEN_FILE = str(_PROJECT_ROOT / "config" / "youtube_token.json")


def get_authenticated_service():
    """Return an authenticated YouTube API service, refreshing or running OAuth flow as needed."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    if not Path(CLIENT_SECRETS_FILE).exists():
        raise FileNotFoundError(
            f"YouTube OAuth client secrets not found at: {CLIENT_SECRETS_FILE}\n\n"
            "To set up:\n"
            "  1. Go to https://console.cloud.google.com/\n"
            "  2. Create a project and enable the YouTube Data API v3\n"
            "  3. Create OAuth2 credentials (type: Desktop app)\n"
            "  4. Download the JSON file and save it as config/youtube_oauth_client.json\n"
            "  5. Re-run this script — a browser window will open for authorisation"
        )

    credentials = None

    if Path(TOKEN_FILE).exists():
        with open(TOKEN_FILE) as f:
            token_data = json.load(f)
        credentials = Credentials.from_authorized_user_info(token_data, SCOPES)

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        with open(TOKEN_FILE, "w") as f:
            f.write(credentials.to_json())

    if not credentials or not credentials.valid:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
        credentials = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(credentials.to_json())

    return build("youtube", "v3", credentials=credentials)


def _parse_iso8601_duration(duration_iso: str) -> tuple[int, str]:
    """Parse ISO 8601 duration (e.g. PT12M34S) → (seconds, 'MM:SS' string)."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_iso or "")
    if not m:
        return 0, ""
    hours = int(m.group(1) or 0)
    mins  = int(m.group(2) or 0)
    secs  = int(m.group(3) or 0)
    duration_seconds = hours * 3600 + mins * 60 + secs
    duration_string  = f"{hours}:{mins:02d}:{secs:02d}" if hours else f"{mins}:{secs:02d}"
    return duration_seconds, duration_string


def get_video_metadata(service, video_id: str) -> dict:
    """Fetch full metadata for a single video from the YouTube Data API."""
    response = service.videos().list(
        part="snippet,contentDetails,statistics,status",
        id=video_id,
    ).execute()

    items = response.get("items", [])
    if not items:
        return {
            "title": "", "channel": "", "channel_id": "", "description": "",
            "tags": "", "view_count": 0, "like_count": 0, "categories": "",
            "language": "", "thumbnail_url": "", "duration_seconds": 0,
            "duration_string": "", "uploaded_at": "",
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "source": "youtube_api",
        }

    item = items[0]
    snippet        = item.get("snippet", {})
    content        = item.get("contentDetails", {})
    statistics     = item.get("statistics", {})

    title         = snippet.get("title", "")
    channel       = snippet.get("channelTitle", "")
    channel_id    = snippet.get("channelId", "")
    description   = str(snippet.get("description") or "")[:300]
    tags          = ", ".join((snippet.get("tags") or [])[:10])
    language      = snippet.get("defaultLanguage") or snippet.get("defaultAudioLanguage") or ""
    thumbnail_url = snippet.get("thumbnails", {}).get("high", {}).get("url", "")
    uploaded_at   = (snippet.get("publishedAt") or "")[:10]

    duration_seconds, duration_string = _parse_iso8601_duration(content.get("duration", ""))

    view_count = int(statistics.get("viewCount", 0))
    like_count = int(statistics.get("likeCount", 0))

    return {
        "title": title,
        "channel": channel,
        "channel_id": channel_id,
        "description": description,
        "tags": tags,
        "view_count": view_count,
        "like_count": like_count,
        "categories": "",  # requires a separate categoryId lookup — skipped
        "language": language,
        "thumbnail_url": thumbnail_url,
        "duration_seconds": duration_seconds,
        "duration_string": duration_string,
        "uploaded_at": uploaded_at,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "source": "youtube_api",
    }


def get_playlist_videos(service, playlist_id: str):
    """
    Yield all videos from a playlist (handles pagination automatically).

    playlist_id "WL" = Watch Later
    playlist_id "LL" = Liked Videos
    Any other playlist ID from the URL works too.
    """
    request = service.playlistItems().list(
        part="snippet,contentDetails",
        playlistId=playlist_id,
        maxResults=50,
    )

    while request:
        response = request.execute()
        for item in response.get("items", []):
            video_id = item["contentDetails"]["videoId"]
            title    = item["snippet"]["title"]
            # Skip deleted or private videos
            if title in ("Deleted video", "Private video"):
                continue
            yield {
                "video_id": video_id,
                "title": title,
                "added_at": item["snippet"]["publishedAt"][:10],
            }
        request = service.playlistItems().list_next(request, response)


def sync_playlist(playlist_id: str = "WL", fetch_full_metadata: bool = True,
                  playlist_name: str = None) -> dict:
    """
    Sync a YouTube playlist into the knowledge base.

    Args:
        playlist_id: "WL" for Watch Later, "LL" for Liked, or any playlist ID
        fetch_full_metadata: if True, fetch full video details via videos.list
        playlist_name: friendly name used as the source label (e.g. "saved").
            Defaults to the playlist_id if not provided.
    """
    from src.store import storage
    from src.pipeline.ingest import pipeline

    service = get_authenticated_service()

    print(f"Fetching playlist '{playlist_id}'...")
    videos = list(get_playlist_videos(service, playlist_id))
    total  = len(videos)
    print(f"Found {total} videos\n")

    synced = skipped = errors = 0

    for i, entry in enumerate(videos, start=1):
        video_id = entry["video_id"]
        title    = entry["title"]
        note_id  = f"youtube_{playlist_id}_{video_id}"

        # Skip if already fully ingested
        existing = storage.fts.get_by_id(note_id)
        if existing and existing.get("channel"):
            print(f"  ({i}/{total}) Skipping {title} (already ingested)")
            skipped += 1
            continue

        try:
            if fetch_full_metadata:
                meta = get_video_metadata(service, video_id)
            else:
                meta = {
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                }

            url  = f"https://www.youtube.com/watch?v={video_id}"
            text = f"Watch later: {url}\n\nTitle: {meta['title']}"
            if meta.get("channel"):
                text += f"\nChannel: {meta['channel']}"
            if meta.get("description"):
                text += f"\nDescription: {meta['description']}"
            if meta.get("tags"):
                text += f"\nTags: {meta['tags']}"
            if meta.get("uploaded_at"):
                text += f"\nUploaded: {meta['uploaded_at']}"
            if meta.get("duration_string"):
                text += f"\nDuration: {meta['duration_string']}"

            source = f"youtube_{playlist_name}" if playlist_name else f"youtube_{playlist_id}"
            pipeline.ingest(
                text=text,
                source=source,
                note_id=note_id,
                metadata=meta,
            )
            synced += 1
            print(
                f"  ({i}/{total}) {meta['title']} | "
                f"{meta.get('channel', '?')} | {meta.get('duration_string', '?')}"
            )

        except Exception as e:
            print(f"  ({i}/{total}) ERROR for {title}: {e}", file=sys.stderr)
            errors += 1

    print(f"\nDone — {synced} synced, {skipped} skipped, {errors} errors")
    return {"synced": synced, "skipped": skipped, "errors": errors}
