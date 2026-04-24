import mcp.types as types
from src.store import storage

LIST_TOOL = types.Tool(
    name="list_items",
    description=(
        "Browse all items in the knowledge base by type or source. "
        "Use this to see everything of a given type, e.g. all videos, all articles. "
        "For topic-based queries use search_knowledge instead."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "content_type": {
                "type": "string",
                "enum": ["video", "article", "note", "list", "doc"],
                "description": "Filter to a specific content type",
            },
            "source": {
                "type": "string",
                "description": "Filter by source e.g. 'obsidian', 'inbox'",
            },
            "limit": {
                "type": "integer",
                "description": "Number of items to return. Use offset for pagination when there are many items.",
                "default": 50,
                "maximum": 200,
            },
            "offset": {
                "type": "integer",
                "description": "Pagination offset",
                "default": 0,
            },
        },
        "required": [],
    },
)


async def handle_list(arguments: dict) -> list[types.TextContent]:
    content_type = arguments.get("content_type")
    source = arguments.get("source")
    limit = min(int(arguments.get("limit", 50)), 200)
    offset = int(arguments.get("offset", 0))

    results = storage.fts.list_notes(content_type, source, limit, offset)
    total = storage.fts.count_notes(content_type, source)

    if not results:
        return [types.TextContent(type="text", text="No items found matching those filters.")]

    header_lines = [f"Showing {len(results)} of {total} items"]
    if content_type:
        header_lines.append(f"  filtered by type: {content_type}")
    if source:
        header_lines.append(f"  filtered by source: {source}")
    header_lines.append("")

    item_lines = []
    for r in results:
        item_lines.append(f"• {r.get('title') or r['id']}")
        item_lines.append(
            f"  {r.get('content_type', '?')} | {r.get('source', '?')} | {r.get('created_at', '?')}"
        )
        if r.get("url"):
            item_lines.append(f"  {r['url']}")
        item_lines.append("")

    footer_lines = []
    if total > offset + limit:
        footer_lines.append(f"  (use offset={offset + limit} to see more)")

    text = "\n".join(header_lines + item_lines + footer_lines)
    return [types.TextContent(type="text", text=text)]
