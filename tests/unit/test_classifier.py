import pytest
from src.pipeline.classifier import detect_urls, classify_content


class TestDetectUrls:

    def test_detects_https_url(self):
        text = "Check this out: https://www.example.com"
        urls = detect_urls(text)
        assert "https://www.example.com" in urls

    def test_detects_youtube_url(self):
        text = "Watch: https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        urls = detect_urls(text)
        assert any("youtube.com" in u for u in urls)

    def test_detects_multiple_urls(self):
        text = "Links: https://google.com and https://github.com"
        urls = detect_urls(text)
        assert len(urls) == 2

    def test_deduplicates_same_url(self):
        url = "https://example.com"
        text = f"{url} and again {url}"
        urls = detect_urls(text)
        assert urls.count(url) == 1

    def test_no_urls_returns_empty_list(self):
        text = "No links here at all"
        urls = detect_urls(text)
        assert urls == []

    def test_handles_url_with_query_params(self):
        url = "https://youtube.com/watch?v=abc123&t=42s"
        text = f"Watch: {url}"
        urls = detect_urls(text)
        assert any("v=abc123" in u for u in urls)


class TestClassifyContent:

    def test_youtube_url_classifies_as_video(self):
        urls = ["https://www.youtube.com/watch?v=abc123"]
        assert classify_content("some text", urls) == "video"

    def test_youtu_be_url_classifies_as_video(self):
        urls = ["https://youtu.be/abc123"]
        assert classify_content("some text", urls) == "video"

    def test_vimeo_classifies_as_video(self):
        urls = ["https://vimeo.com/123456"]
        assert classify_content("some text", urls) == "video"

    def test_non_video_url_classifies_as_article(self):
        urls = ["https://www.example.com/blog/post"]
        assert classify_content("some text", urls) == "article"

    def test_no_url_classifies_as_note(self):
        assert classify_content("Just a plain note", []) == "note"

    def test_list_content_classifies_as_list(self):
        # Needs > 3 list-marker lines to trigger "list" classification
        text = "- item one\n- item two\n- item three\n- item four"
        assert classify_content(text, []) == "list"
