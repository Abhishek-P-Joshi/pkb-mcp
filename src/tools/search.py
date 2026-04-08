import mcp.types as types
from src.store import storage
from src.store.search import hybrid_search

SEARCH_TOOL = types.Tool(
    name="search_knowledge",
    description=(
        "Search the personal knowledge base using a query. Combines keyword and semantic search. "
        "Use content_type to filter to videos, articles, or notes. Use source to filter by where "
        "the note came from. Always use this before answer_question."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to search for",
            },
            "content_type": {
                "type": "string",
                "enum": ["video", "article", "note", "list", "doc"],
                "description": "Filter to a specific content type",
            },
            "source": {
                "type": "string",
                "description": "Filter by source e.g. 'obsidian', 'inbox', 'apple_notes'",
            },
            "limit": {
                "type": "integer",
                "description": "Number of results to return (max 25)",
                "default": 10,
                "maximum": 25,
            },
            "min_score": {
                "type": "number",
                "description": (
                    "Minimum relevance score (0-1). Default 0.02. "
                    "Lower to get more results, raise to get only highly confident matches."
                ),
                "default": 0.02,
            },
            "fts_only": {
                "type": "boolean",
                "description": "Set true for exact keyword searches (URLs, names, IDs)",
                "default": False,
            },
        },
        "required": ["query"],
    },
)


async def handle_search(arguments: dict) -> list[types.TextContent]:
    query = arguments["query"]
    content_type = arguments.get("content_type")
    source = arguments.get("source")
    limit = min(int(arguments.get("limit", 10)), 25)
    min_score = float(arguments.get("min_score", 0.02))
    fts_only = bool(arguments.get("fts_only", False))

    if fts_only:
        raw = storage.fts.search(query, content_type=content_type, limit=limit)
        if not raw:
            return [types.TextContent(
                type="text",
                text=f"No results found for '{query}'. Try broader search terms.",
            )]
        lines = [f"Found {len(raw)} results for '{query}' (keyword search)\n"]
        for r in raw:
            lines.append(f"• {r.get('title') or r['id']}")
            lines.append(f"  Type: {r.get('content_type', '?')} | Source: {r.get('source', '?')}")
            if r.get("url"):
                lines.append(f"  {r['url']}")
            snippet = (r.get("raw_text") or "")[:200]
            if snippet:
                lines.append(f"  {snippet}")
            lines.append("")
        return [types.TextContent(type="text", text="\n".join(lines))]

    results = hybrid_search(query, content_type=content_type, source=source, limit=limit, min_score=min_score)

    if not results:
        return [types.TextContent(
            type="text",
            text=(
                f"No results found for '{query}' above the confidence threshold ({min_score}). "
                "Try broader search terms or lower the min_score."
            ),
        )]

    lines = [f"Found {len(results)} result{'s' if len(results) != 1 else ''} for '{query}'\n"]
    for r in results:
        meta = r.get("metadata", {})
        title = meta.get("title") or r["note_id"]
        lines.append(f"• {title}")
        lines.append(
            f"  Type: {meta.get('content_type', '?')} | "
            f"Source: {meta.get('source', '?')} | "
            f"Score: {r['rrf_score']}"
        )
        if meta.get("url"):
            lines.append(f"  {meta['url']}")
        if r.get("excerpt"):
            lines.append(f"  {r['excerpt']}")
        lines.append("")

    return [types.TextContent(type="text", text="\n".join(lines))]
