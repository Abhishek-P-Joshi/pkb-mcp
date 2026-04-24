import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

pytestmark = pytest.mark.smoke

# These tests import tool handlers directly and call them without going
# through the MCP protocol — faster than a full e2e server round-trip.
# They run against a temporary test database, not the production one.


@pytest.fixture(scope="session", autouse=True)
def smoke_test_storage(tmp_path_factory):
    """
    Redirects the storage singleton to a temporary database
    for the duration of the smoke test session.
    Production database is never touched.
    """
    tmp = tmp_path_factory.mktemp("smoke_db")
    (tmp / "chroma").mkdir()
    (tmp / "sqlite").mkdir()

    from src.config import Config, config
    test_config = Config(
        env="test",
        transport=config.transport,
        host=config.host,
        port=config.port,
        auth_enabled=False,
        storage_path=tmp,
        embedding_model=config.embedding_model,
        sync_interval_minutes=config.sync_interval_minutes,
        youtube_sync_enabled=False,
        obsidian_vault_path="",
    )

    with patch("src.store.fts.config", test_config), \
         patch("src.store.vector.config", test_config):
        from src.store.fts import FTSStore
        from src.store.vector import VectorStore
        test_fts = FTSStore()
        test_vector = VectorStore()

        # Mutate the existing singleton in-place so all tool handlers that
        # already hold `from src.store import storage` see the test stores.
        import src.store as store_module
        original_fts = store_module.storage.fts
        original_vector = store_module.storage.vector
        store_module.storage.fts = test_fts
        store_module.storage.vector = test_vector
        yield
        store_module.storage.fts = original_fts
        store_module.storage.vector = original_vector


@pytest.fixture(autouse=True)
def seed_smoke_data():
    from src.store import storage
    storage.fts.upsert({
        "id": "smoke_seed_001",
        "source": "manual",
        "content_type": "note",
        "title": "Smoke test seed note",
        "url": "",
        "tags": "smoke,test",
        "file_hash": "smoke_hash_001",
        "raw_text": "Chess openings and astrophysics and machine learning",
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
    })


@pytest.mark.asyncio
async def test_health_check_returns_ok():
    from src.tools.health import handle_health_check
    results = await handle_health_check()
    assert len(results) == 1
    assert "status: ok" in results[0].text


@pytest.mark.asyncio
async def test_list_items_returns_results():
    from src.tools.list_items import handle_list
    results = await handle_list({"limit": 5})
    assert len(results) == 1
    # seed_smoke_data guarantees at least one item exists
    assert "Showing" in results[0].text


@pytest.mark.asyncio
async def test_search_knowledge_returns_results():
    from src.tools.search import handle_search
    results = await handle_search({
        "query": "chess",
        "min_score": 0.01,
        "limit": 5,
    })
    assert len(results) == 1
    assert isinstance(results[0].text, str)


@pytest.mark.asyncio
async def test_browse_knowledge_count_only():
    from src.tools.browse import handle_browse
    results = await handle_browse({
        "content_type": "video",
        "count_only": True,
    })
    assert len(results) == 1
    assert "Total:" in results[0].text


@pytest.mark.asyncio
async def test_ingest_and_retrieve_roundtrip():
    from src.tools.ingest import handle_ingest_content
    from src.store import storage

    result = await handle_ingest_content({
        "text": "Smoke test note about solar system planets",
        "source": "manual",
        "note_id": "smoke_test_roundtrip_001",
    })
    assert len(result) == 1
    assert "ok" in result[0].text.lower() or "skipped" in result[0].text.lower()

    # Use the already-patched singleton, not a freshly constructed FTSStore
    note = storage.fts.get_by_id("smoke_test_roundtrip_001")
    assert note is not None
