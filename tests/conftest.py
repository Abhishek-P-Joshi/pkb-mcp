import pytest
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch
from src.config import Config

@pytest.fixture
def temp_dir(tmp_path):
    """A temporary directory that cleans itself up."""
    return tmp_path

@pytest.fixture
def test_config(tmp_path):
    """A Config instance pointing at a temp directory."""
    storage = tmp_path / "data"
    (storage / "chroma").mkdir(parents=True)
    (storage / "sqlite").mkdir(parents=True)
    return Config(
        env="test",
        transport="stdio",
        host="localhost",
        port=8000,
        auth_enabled=False,
        storage_path=storage,
        embedding_model="all-MiniLM-L6-v2",
        sync_interval_minutes=60,
        youtube_sync_enabled=False,
        obsidian_vault_path="",
    )

@pytest.fixture
def temp_fts_store(test_config, monkeypatch):
    """A FTSStore backed by a temp SQLite database."""
    from src.store.fts import FTSStore
    monkeypatch.setattr("src.store.fts.config", test_config)
    store = FTSStore()
    yield store

@pytest.fixture
def sample_note():
    """A minimal valid note dict for testing."""
    return {
        "id": "test_note_001",
        "source": "manual",
        "content_type": "note",
        "title": "Test note",
        "url": "",
        "tags": "test,sample",
        "file_hash": "abc123",
        "raw_text": "This is a test note about astrophysics and black holes.",
        "channel": None,
        "channel_id": None,
        "uploaded_at": None,
        "duration_seconds": None,
        "duration_string": None,
        "view_count": None,
        "like_count": None,
        "categories": None,
        "language": None,
        "thumbnail_url": None,
    }

@pytest.fixture
def sample_video_note():
    """A video note with full YouTube metadata."""
    return {
        "id": "test_video_001",
        "source": "youtube_watch_later",
        "content_type": "video",
        "title": "How Neutron Stars Form",
        "url": "https://www.youtube.com/watch?v=abc123",
        "tags": "space,physics,astronomy",
        "file_hash": "def456",
        "raw_text": "Watch later: https://www.youtube.com/watch?v=abc123\nTitle: How Neutron Stars Form\nChannel: PBS Space Time\nDescription: An exploration of neutron star formation.",
        "channel": "PBS Space Time",
        "channel_id": "UC_channel_id",
        "uploaded_at": "2023-06-15",
        "duration_seconds": 743,
        "duration_string": "12:23",
        "view_count": 1500000,
        "like_count": 45000,
        "categories": "Education,Science & Technology",
        "language": "en",
        "thumbnail_url": "https://i.ytimg.com/vi/abc123/hqdefault.jpg",
    }
