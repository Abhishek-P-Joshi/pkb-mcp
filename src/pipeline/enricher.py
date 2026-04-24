import re
import sys
import httpx
import yt_dlp


_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class URLEnricher:
    """Fetches metadata from web pages and YouTube videos."""

    def enrich(self, url: str) -> dict:
        if "youtube.com/watch" in url or "youtu.be/" in url:
            return self.enrich_youtube(url)
        return self.enrich_url(url)

    def enrich_url(self, url: str) -> dict:
        """Fetch a web page and extract title and meta description."""
        try:
            response = httpx.get(
                url,
                timeout=10,
                follow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
            )
            response.raise_for_status()
            html = response.text

            # Extract <title>
            title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
            raw_title = title_match.group(1).strip() if title_match else ""
            # Strip common " | Site Name" or " - Site Name" suffixes
            title = re.split(r"\s*[\|–—-]\s+\S", raw_title)[0].strip() if raw_title else ""

            # Extract meta description
            desc_match = re.search(
                r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
                html,
                re.IGNORECASE,
            )
            if not desc_match:
                # Try alternate attribute order
                desc_match = re.search(
                    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
                    html,
                    re.IGNORECASE,
                )
            description = desc_match.group(1).strip() if desc_match else ""

            return {"title": title, "description": description, "url": url, "source": "web"}

        except Exception as e:
            print(f"[enricher] Failed to fetch {url}: {e}", file=sys.stderr)
            return {"title": "", "description": "", "url": url, "source": "web"}

    def enrich_youtube(self, url: str) -> dict:
        """Extract metadata from a YouTube video using yt-dlp."""
        try:
            opts = {"quiet": True, "no_warnings": True, "extract_flat": False}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)

            title = info.get("title", "")
            channel = info.get("channel") or info.get("uploader", "")
            channel_id = info.get("channel_id") or info.get("uploader_id", "")
            description = str(info.get("description") or "")[:300]
            tags = ", ".join((info.get("tags") or [])[:10])
            view_count = info.get("view_count")
            like_count = info.get("like_count")
            categories = ", ".join(info.get("categories") or [])
            thumbnail_url = info.get("thumbnail", "")

            # Language — prefer explicit field, fall back to first subtitle track
            language = info.get("language") or ""
            if not language:
                subtitles = info.get("subtitles") or {}
                keys = list(subtitles.keys())
                language = keys[0] if keys else ""

            # Duration
            duration_seconds = info.get("duration")
            if duration_seconds:
                h = duration_seconds // 3600
                m = (duration_seconds % 3600) // 60
                s = duration_seconds % 60
                duration_string = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
            else:
                duration_string = ""

            # Upload date — yt-dlp returns "YYYYMMDD"
            raw_date = info.get("upload_date", "")
            uploaded_at = (
                f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
                if len(raw_date) == 8 else ""
            )

            return {
                "title": title,
                "channel": channel,
                "channel_id": channel_id,
                "description": description,
                "tags": tags,
                "view_count": view_count,
                "like_count": like_count,
                "categories": categories,
                "language": language,
                "thumbnail_url": thumbnail_url,
                "duration_seconds": duration_seconds,
                "duration_string": duration_string,
                "uploaded_at": uploaded_at,
                "url": url,
                "source": "youtube",
            }

        except Exception as e:
            print(f"[enricher] Failed to fetch YouTube metadata for {url}: {e}", file=sys.stderr)
            return {
                "title": "", "channel": "", "channel_id": "", "description": "",
                "tags": "", "view_count": None, "like_count": None, "categories": "",
                "language": "", "thumbnail_url": "", "duration_seconds": None,
                "duration_string": "", "uploaded_at": "", "url": url, "source": "youtube",
            }


if __name__ == "__main__":
    enricher = URLEnricher()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    print(f"Fetching metadata for: {url}\n")
    result = enricher.enrich(url)
    for k, v in result.items():
        print(f"  {k}: {v}")
