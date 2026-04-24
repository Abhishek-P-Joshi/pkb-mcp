from src.store.fts import FTSStore
from src.store.vector import VectorStore
from src.store import storage


def reciprocal_rank_fusion(
    fts_results: list[dict],
    vector_results: list[dict],
    k: int = 60,
) -> list[dict]:
    """
    Merge FTS and vector results into a single ranked list using RRF.
    Scores are accumulated per note_id (not chunk id).
    """
    scores = {}
    fts_ranks = {}
    vector_ranks = {}
    best_chunk = {}  # note_id -> best vector result (highest score)

    for rank, result in enumerate(fts_results):
        note_id = result["id"]
        scores[note_id] = scores.get(note_id, 0) + 1 / (k + rank + 1)
        fts_ranks[note_id] = rank

    for rank, result in enumerate(vector_results):
        note_id = result["metadata"]["note_id"]
        scores[note_id] = scores.get(note_id, 0) + 1 / (k + rank + 1)
        vector_ranks[note_id] = rank
        # Keep the chunk with the highest similarity score
        if note_id not in best_chunk or result["score"] > best_chunk[note_id]["score"]:
            best_chunk[note_id] = result

    sorted_ids = sorted(scores, key=lambda nid: scores[nid], reverse=True)

    merged = []
    for note_id in sorted_ids:
        chunk = best_chunk.get(note_id, {})
        excerpt = (chunk.get("text") or "")[:200]
        metadata = chunk.get("metadata", {})
        merged.append({
            "note_id": note_id,
            "rrf_score": round(scores[note_id], 4),
            "fts_rank": fts_ranks.get(note_id),
            "vector_rank": vector_ranks.get(note_id),
            "excerpt": excerpt,
            "metadata": metadata,
        })

    return merged


def hybrid_search(
    query: str,
    content_type: str = None,
    source: str = None,
    limit: int = 20,
    min_score: float = 0.015,
) -> list[dict]:
    """
    Hybrid search combining FTS and vector results via RRF.
    Optionally filter by content_type, source, and minimum RRF score.
    """
    fts_results = storage.fts.search(query, content_type=content_type, limit=limit * 3)
    vector_results = storage.vector.search(query, content_type=content_type, n_results=limit * 3)

    if source:
        fts_results = [r for r in fts_results if r.get("source") == source]
        vector_results = [r for r in vector_results if r.get("metadata", {}).get("source") == source]

    merged = reciprocal_rank_fusion(fts_results, vector_results)
    merged = [r for r in merged if r["rrf_score"] >= min_score]
    return merged[:limit]


if __name__ == "__main__":
    import sqlite3
    conn = sqlite3.connect(storage.fts.db_path)
    count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    conn.close()

    if count == 0:
        print("No data yet — ingest some notes first")
    else:
        query = "astrophysics"
        results = hybrid_search(query)
        if not results:
            print(f"No results found for '{query}' above the confidence threshold (0.02). "
                  "Try broader search terms or lower the min_score.")
        else:
            print(f"Found {len(results)} result{'s' if len(results) != 1 else ''} for '{query}'\n")
            for r in results:
                title = r["metadata"].get("title") or r["note_id"]
                content_type = r["metadata"].get("content_type", "?")
                source = r["metadata"].get("source", "?")
                print(f"- {title}")
                print(f"  Type: {content_type} | Source: {source} | Score: {r['rrf_score']}")
                print(f"  excerpt: {r['excerpt'][:80]}...")
                print()
