import re


def detect_urls(text: str) -> list[str]:
    """Extract all unique http/https URLs from a text string."""
    pattern = r'https?://[^\s\]\[<>"\']+(?:\?[^\s\]\[<>"\']*)?'
    found = re.findall(pattern, text)
    # Deduplicate while preserving order
    seen = set()
    result = []
    for url in found:
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def classify_content(text: str, urls: list[str]) -> str:
    """Classify text into a content type based on URLs and structure."""
    for url in urls:
        if "youtube.com/watch" in url or "youtu.be/" in url:
            return "video"
        if "vimeo.com" in url:
            return "video"

    if len(urls) > 0:
        return "article"

    list_pattern = re.compile(r'^(\s*[-*•]|\s*\d+[.)]\s)', re.MULTILINE)
    list_lines = list_pattern.findall(text)
    if len(list_lines) > 3:
        return "list"

    return "note"


if __name__ == "__main__":
    tests = [
        (
            "video (YouTube)",
            "Check out this talk https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        ),
        (
            "video (Vimeo)",
            "Great short film at https://vimeo.com/123456789",
        ),
        (
            "article",
            "Interesting read: https://example.com/article about machine learning.",
        ),
        (
            "list",
            "Shopping list:\n- Apples\n- Bread\n- Milk\n* Eggs\n* Butter\n• Coffee",
        ),
        (
            "note",
            "Today I learned that chunking text into overlapping windows helps "
            "preserve semantic context at boundaries.",
        ),
    ]

    for label, text in tests:
        urls = detect_urls(text)
        content_type = classify_content(text, urls)
        status = "✓" if content_type == label.split()[0] else "✗"
        print(f"{status} [{label}] → detected: '{content_type}'  urls={urls}")
