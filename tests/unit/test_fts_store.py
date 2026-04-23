import pytest
from src.store.fts import FTSStore


class TestFTSStoreUpsertAndRetrieve:

    def test_upsert_and_get_by_id(self, temp_fts_store, sample_note):
        temp_fts_store.upsert(sample_note)
        result = temp_fts_store.get_by_id("test_note_001")
        assert result is not None
        assert result["title"] == "Test note"
        assert result["source"] == "manual"

    def test_upsert_updates_existing_note(self, temp_fts_store, sample_note):
        temp_fts_store.upsert(sample_note)
        sample_note["title"] = "Updated title"
        temp_fts_store.upsert(sample_note)
        result = temp_fts_store.get_by_id("test_note_001")
        assert result["title"] == "Updated title"

    def test_get_by_id_returns_none_for_missing(self, temp_fts_store):
        result = temp_fts_store.get_by_id("nonexistent_id")
        assert result is None

    def test_get_by_hash_finds_note(self, temp_fts_store, sample_note):
        temp_fts_store.upsert(sample_note)
        result = temp_fts_store.get_by_hash("abc123", "test_note_001")
        assert result is not None

    def test_get_by_hash_scoped_to_note_id(self, temp_fts_store, sample_note):
        temp_fts_store.upsert(sample_note)
        # Same hash, different note_id should return None
        result = temp_fts_store.get_by_hash("abc123", "different_note_id")
        assert result is None

    def test_get_by_hash_without_note_id(self, temp_fts_store, sample_note):
        temp_fts_store.upsert(sample_note)
        result = temp_fts_store.get_by_hash("abc123")
        assert result is not None


class TestFTSStoreSearch:

    def test_search_finds_matching_note(self, temp_fts_store, sample_note):
        temp_fts_store.upsert(sample_note)
        results = temp_fts_store.search("astrophysics")
        assert len(results) > 0
        assert results[0]["id"] == "test_note_001"

    def test_search_returns_empty_for_no_match(self, temp_fts_store, sample_note):
        temp_fts_store.upsert(sample_note)
        results = temp_fts_store.search("completely unrelated quantum xyz")
        assert results == []

    def test_search_filters_by_content_type(self, temp_fts_store, sample_note,
                                             sample_video_note):
        temp_fts_store.upsert(sample_note)
        temp_fts_store.upsert(sample_video_note)
        # "astrophysics" only appears in the plain note; with content_type="video" it must be absent
        results = temp_fts_store.search("astrophysics", content_type="video")
        ids = [r["id"] for r in results]
        assert "test_note_001" not in ids

    def test_search_sanitises_special_characters(self, temp_fts_store, sample_note):
        # Should not raise FTS5 syntax error
        results = temp_fts_store.search("what is astrophysics?")
        assert isinstance(results, list)

    def test_search_handles_url_query(self, temp_fts_store, sample_video_note):
        temp_fts_store.upsert(sample_video_note)
        results = temp_fts_store.search("youtube.com/watch?v=abc123")
        assert isinstance(results, list)


class TestFTSStoreListAndFilter:

    def test_list_notes_returns_all(self, temp_fts_store, sample_note,
                                    sample_video_note):
        temp_fts_store.upsert(sample_note)
        temp_fts_store.upsert(sample_video_note)
        results = temp_fts_store.list_notes()
        assert len(results) == 2

    def test_list_notes_filters_by_content_type(self, temp_fts_store, sample_note,
                                                  sample_video_note):
        temp_fts_store.upsert(sample_note)
        temp_fts_store.upsert(sample_video_note)
        results = temp_fts_store.list_notes(content_type="video")
        assert len(results) == 1
        assert results[0]["content_type"] == "video"

    def test_count_notes_returns_correct_count(self, temp_fts_store, sample_note,
                                                sample_video_note):
        temp_fts_store.upsert(sample_note)
        temp_fts_store.upsert(sample_video_note)
        assert temp_fts_store.count_notes() == 2
        assert temp_fts_store.count_notes(content_type="video") == 1

    def test_filter_by_channel(self, temp_fts_store, sample_video_note):
        temp_fts_store.upsert(sample_video_note)
        results = temp_fts_store.filter_by_date(channel="PBS Space Time")
        assert len(results) == 1

    def test_filter_by_channel_partial_match(self, temp_fts_store, sample_video_note):
        temp_fts_store.upsert(sample_video_note)
        # filter_by_date uses LIKE %channel%, so partial name works
        results = temp_fts_store.filter_by_date(channel="PBS")
        assert len(results) == 1

    def test_filter_by_uploaded_after(self, temp_fts_store, sample_video_note):
        temp_fts_store.upsert(sample_video_note)
        results = temp_fts_store.filter_by_date(uploaded_after="2023-01-01")
        assert len(results) == 1
        results_before = temp_fts_store.filter_by_date(uploaded_after="2024-01-01")
        assert len(results_before) == 0

    def test_filter_by_max_duration(self, temp_fts_store, sample_video_note):
        temp_fts_store.upsert(sample_video_note)
        # sample_video_note duration_seconds=743; 900 allows it, 60 excludes it
        results = temp_fts_store.filter_by_date(max_duration_seconds=900)
        assert len(results) == 1
        results_short = temp_fts_store.filter_by_date(max_duration_seconds=60)
        assert len(results_short) == 0

    def test_pagination_with_limit_and_offset(self, temp_fts_store, sample_note,
                                               sample_video_note):
        temp_fts_store.upsert(sample_note)
        temp_fts_store.upsert(sample_video_note)
        page1 = temp_fts_store.list_notes(limit=1, offset=0)
        page2 = temp_fts_store.list_notes(limit=1, offset=1)
        assert len(page1) == 1
        assert len(page2) == 1
        assert page1[0]["id"] != page2[0]["id"]
