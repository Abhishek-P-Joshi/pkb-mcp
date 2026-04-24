import pytest
from unittest.mock import patch, MagicMock
from src.pipeline.ingest import IngestPipeline

MOCK_ENRICHED = {
    "title": "How Neutron Stars Form",
    "channel": "PBS Space Time",
    "channel_id": "UC_test",
    "description": "An exploration of stellar collapse.",
    "tags": "space, physics, astronomy",
    "uploaded_at": "2023-06-15",
    "duration_seconds": 743,
    "duration_string": "12:23",
    "view_count": 1500000,
    "like_count": 45000,
    "categories": "Education",
    "language": "en",
    "thumbnail_url": "https://i.ytimg.com/vi/test/hqdefault.jpg",
    "url": "https://www.youtube.com/watch?v=test123",
    "source": "youtube_api",
}


# WHY WE PATCH storage NOT config:
# IngestPipeline imports `storage` at module load time
# (from src.store import storage). By the time the test runs,
# that import has already resolved to the production singleton.
# Patching config after the fact has no effect on an already-
# constructed object. The correct approach is to patch the
# storage object directly so the pipeline uses the test db.
# Any new connector that imports storage at module level needs
# the same treatment.
@pytest.fixture
def pipeline(test_config, mock_embedder, monkeypatch):
    # Patch config for both stores before constructing anything
    monkeypatch.setattr("src.store.fts.config", test_config)
    monkeypatch.setattr("src.store.vector.config", test_config)

    # Prevent SentenceTransformer from loading (~90MB model) in both places
    # that eagerly load it at __init__ time: Embedder and VectorStore.
    # We replace p.embedder below, so the Embedder() construction is wasted
    # work; patching here avoids paying that cost per test.
    from unittest.mock import MagicMock
    monkeypatch.setattr("src.pipeline.embedder.SentenceTransformer", MagicMock)
    monkeypatch.setattr("src.store.vector.SentenceTransformer", MagicMock)

    # Build an isolated StorageManager pointing at the temp paths
    from src.store import StorageManager
    test_storage = StorageManager()

    # Replace the module-level singleton that IngestPipeline.ingest() calls
    monkeypatch.setattr("src.pipeline.ingest.storage", test_storage)

    p = IngestPipeline()
    p.embedder = mock_embedder    # fake vectors, instant
    p.storage = test_storage      # expose for assertions
    return p


class TestIngestPipeline:

    def test_ingest_plain_text_note(self, pipeline):
        result = pipeline.ingest(
            text="This is a test note about machine learning.",
            source="manual",
            note_id="test_plain_001",
        )
        assert result["status"] == "ok"
        assert result["content_type"] == "note"
        assert result["chunks"] >= 1

    def test_ingest_youtube_url_classifies_as_video(self, pipeline):
        with patch.object(pipeline.enricher, "enrich", return_value=MOCK_ENRICHED):
            result = pipeline.ingest(
                text="Watch: https://www.youtube.com/watch?v=test123",
                source="manual",
                note_id="test_video_001",
            )
        assert result["status"] == "ok"
        assert result["content_type"] == "video"

    def test_ingest_with_pre_fetched_metadata_skips_enrichment(self, pipeline):
        with patch.object(pipeline.enricher, "enrich") as mock_enrich:
            pipeline.ingest(
                text="Watch: https://www.youtube.com/watch?v=test123",
                source="manual",
                note_id="test_meta_001",
                metadata=MOCK_ENRICHED,
            )
            mock_enrich.assert_not_called()

    def test_deduplication_skips_unchanged_file(self, pipeline):
        pipeline.ingest(
            text="Original content about chess openings.",
            source="manual",
            note_id="test_dedup_001",
            file_hash="hash_abc123",
        )
        result = pipeline.ingest(
            text="Original content about chess openings.",
            source="manual",
            note_id="test_dedup_001",
            file_hash="hash_abc123",
        )
        assert result["status"] == "skipped"
        assert result["reason"] == "unchanged"

    def test_same_content_different_note_id_both_ingest(self, pipeline):
        text = "Identical content about black holes."
        result1 = pipeline.ingest(text=text, source="manual",
                                   note_id="note_a", file_hash="same_hash")
        result2 = pipeline.ingest(text=text, source="manual",
                                   note_id="note_b", file_hash="same_hash")
        assert result1["status"] == "ok"
        assert result2["status"] == "ok"

    def test_ingest_stores_note_in_fts(self, pipeline):
        pipeline.ingest(
            text="A note about quantum mechanics and wave functions.",
            source="manual",
            note_id="test_fts_001",
        )
        # Use pipeline.storage (the isolated test store) not the global singleton
        result = pipeline.storage.fts.get_by_id("test_fts_001")
        assert result is not None
        assert result["source"] == "manual"

    def test_long_text_produces_multiple_chunks_in_vector_store(self, pipeline):
        long_text = " ".join(["The study of astrophysics"] * 100)
        result = pipeline.ingest(
            text=long_text,
            source="manual",
            note_id="test_chunks_001",
        )
        assert result["chunks"] > 1

    def test_list_content_classified_correctly(self, pipeline):
        list_text = "- milk\n- eggs\n- bread\n- butter\n- cheese"
        result = pipeline.ingest(
            text=list_text,
            source="manual",
            note_id="test_list_001",
        )
        assert result["content_type"] == "list"
