import pytest

pytestmark = pytest.mark.smoke

# These tests import tool handlers directly and call them without going
# through the MCP protocol — faster than a full e2e server round-trip.
# They run against the LIVE production database.


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
    # Either there is data ("Showing …") or the KB is empty ("No items found")
    assert "Showing" in results[0].text or "No items found" in results[0].text


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
    from src.store.fts import FTSStore

    result = await handle_ingest_content({
        "text": "Smoke test note about solar system planets",
        "source": "manual",
        "note_id": "smoke_test_roundtrip_001",
    })
    assert len(result) == 1
    assert "ok" in result[0].text.lower() or "skipped" in result[0].text.lower()

    store = FTSStore()
    note = store.get_by_id("smoke_test_roundtrip_001")
    assert note is not None
