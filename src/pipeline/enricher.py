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
            description = (info.get("description") or "")[:500]
            channel = info.get("channel") or info.get("uploader", "")
            tags = ", ".join((info.get("tags") or [])[:10])

            return {
                "title": title,
                "description": description,
                "channel": channel,
                "tags": tags,
                "url": url,
                "source": "youtube",
            }

        except Exception as e:
            print(f"[enricher] Failed to fetch YouTube metadata for {url}: {e}", file=sys.stderr)
            return {"title": "", "description": "", "channel": "", "tags": "", "url": url, "source": "youtube"}


if __name__ == "__main__":
    enricher = URLEnricher()
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    print(f"Fetching metadata for: {url}\n")
    result = enricher.enrich(url)
    for k, v in result.items():
        print(f"  {k}: {v}")
