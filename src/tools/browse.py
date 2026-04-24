import mcp.types as types
from src.store import storage

BROWSE_TOOL = types.Tool(
    name="browse_knowledge",
    description="""Browse the knowledge base using structured filters.
Use this tool (NOT search_knowledge) when the user asks:
- Time/date: 'videos from last month', 'recently saved',
  'saved in 2024', 'uploaded this year', 'oldest videos'
- Channel: 'Kurzgesagt videos', 'videos by 3Blue1Brown',
  'agadmator chess games'
- Duration: 'short videos under 10 minutes', 'long documentaries'
- Popularity: 'most viewed videos I saved', 'popular science videos'
- Language: 'Hindi videos', 'non-English content'
- Category: 'Education category videos', 'Entertainment videos'
- Counts: 'how many chess videos', 'how many videos total'
- Sorting: 'latest videos', 'oldest saved', 'most views'
Use search_knowledge for topic/concept queries like
'videos about machine learning' or 'notes about astrophysics'.""",
    inputSchema={
        "type": "object",
        "properties": {
            "content_type": {
                "type": "string",
                "enum": ["video", "article", "note", "list", "doc"],
            },
            "source": {
                "type": "string",
            },
            "channel": {
                "type": "string",
                "description": "Filter by YouTube channel name (partial match)",
            },
            "language": {
                "type": "string",
                "description": "ISO language code e.g. 'en', 'hi', 'es'",
            },
            "categories": {
                "type": "string",
                "description": "Filter by YouTube category e.g. 'Education'",
            },
            "uploaded_after": {
                "type": "string",
                "description": "ISO date YYYY-MM-DD",
            },
            "uploaded_before": {
                "type": "string",
                "description": "ISO date YYYY-MM-DD",
            },
            "ingested_after": {
                "type": "string",
                "description": "ISO date YYYY-MM-DD — when you saved it",
            },
            "ingested_before": {
                "type": "string",
                "description": "ISO date YYYY-MM-DD",
            },
            "min_duration_seconds": {
                "type": "integer",
                "description": "Minimum duration in seconds",
            },
            "max_duration_seconds": {
                "type": "integer",
                "description": "Maximum duration in seconds",
            },
            "order_by": {
                "type": "string",
                "enum": ["ingested", "uploaded", "views"],
                "default": "ingested",
            },
            "order_dir": {
                "type": "string",
                "enum": ["DESC", "ASC"],
                "default": "DESC",
            },
            "limit": {
                "type": "integer",
                "default": 20,
                "maximum": 100,
            },
            "offset": {
                "type": "integer",
                "default": 0,
            },
            "count_only": {
                "type": "boolean",
                "default": False,
                "description": "Return count only — use for 'how many' questions",
            },
        },
        "required": [],
    },
)


async def handle_browse(arguments: dict) -> list[types.TextContent]:
    content_type = arguments.get("content_type")
    source = arguments.get("source")
    channel = arguments.get("channel")
    language = arguments.get("language")
    categories = arguments.get("categories")
    uploaded_after = arguments.get("uploaded_after")
    uploaded_before = arguments.get("uploaded_before")
    ingested_after = arguments.get("ingested_after")
    ingested_before = arguments.get("ingested_before")
    min_duration_seconds = arguments.get("min_duration_seconds")
    max_duration_seconds = arguments.get("max_duration_seconds")
    order_by = arguments.get("order_by", "ingested")
    order_dir = arguments.get("order_dir", "DESC")
    limit = min(int(arguments.get("limit", 20)), 100)
    offset = int(arguments.get("offset", 0))
    count_only = bool(arguments.get("count_only", False))

    filter_params = {}
    if content_type is not None:
        filter_params["content_type"] = content_type
    if source is not None:
        filter_params["source"] = source
    if channel is not None:
        filter_params["channel"] = channel
    if language is not None:
        filter_params["language"] = language
    if categories is not None:
        filter_params["categories"] = categories
    if uploaded_after is not None:
        filter_params["uploaded_after"] = uploaded_after
    if uploaded_before is not None:
        filter_params["uploaded_before"] = uploaded_before
    if ingested_after is not None:
        filter_params["ingested_after"] = ingested_after
    if ingested_before is not None:
        filter_params["ingested_before"] = ingested_before
    if min_duration_seconds is not None:
        filter_params["min_duration_seconds"] = min_duration_seconds
    if max_duration_seconds is not None:
        filter_params["max_duration_seconds"] = max_duration_seconds

    if count_only:
        total = storage.fts.count_filtered(**filter_params)
        if not content_type:
            breakdown = {}
            for ct in ["video", "article", "note", "list", "doc"]:
                n = storage.fts.count_filtered(
                    content_type=ct,
                    **{k: v for k, v in filter_params.items() if k != "content_type"},
                )
                if n > 0:
                    breakdown[ct] = n
            lines = [f"Total: {total} items"]
            for ct, n in breakdown.items():
                lines.append(f"  {ct}s: {n}")
            return [types.TextContent(type="text", text="\n".join(lines))]
        return [types.TextContent(type="text", text=f"Total: {total} items")]

    results = storage.fts.filter_by_date(
        **filter_params,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
    )
    total = storage.fts.count_filtered(**filter_params)

    # Build header
    header = f"Showing {len(results)} of {total} items"
    active_filters = []
    if channel:
        active_filters.append(f"channel: {channel}")
    if language:
        active_filters.append(f"language: {language}")
    if categories:
        active_filters.append(f"category: {categories}")
    if uploaded_after:
        active_filters.append(f"uploaded after: {uploaded_after}")
    if uploaded_before:
        active_filters.append(f"uploaded before: {uploaded_before}")
    if min_duration_seconds:
        active_filters.append(f"min duration: {min_duration_seconds // 60}min")
    if max_duration_seconds:
        active_filters.append(f"max duration: {max_duration_seconds // 60}min")
    if active_filters:
        header += "\n  " + " | ".join(active_filters)

    lines = [header, ""]
    for r in results:
        lines.append(f"• {r.get('title', 'Untitled')}")
        meta_parts = []
        if r.get("channel"):
            meta_parts.append(r["channel"])
        if r.get("duration_string"):
            meta_parts.append(r["duration_string"])
        if r.get("view_count"):
            vc = r["view_count"]
            if vc >= 1_000_000:
                meta_parts.append(f"{vc / 1_000_000:.1f}M views")
            elif vc >= 1_000:
                meta_parts.append(f"{vc // 1_000}K views")
            else:
                meta_parts.append(f"{vc} views")
        if r.get("language") and r["language"] != "en":
            meta_parts.append(r["language"].upper())
        if meta_parts:
            lines.append(f"  {' · '.join(meta_parts)}")
        if r.get("uploaded_at"):
            lines.append(
                f"  uploaded: {r['uploaded_at']} | saved: {str(r.get('created_at', ''))[:10]}"
            )
        if r.get("url"):
            lines.append(f"  {r['url']}")
        lines.append("")

    if total > offset + limit:
        lines.append(
            f"(Showing {offset + 1}–{offset + len(results)} of {total}. "
            f"Use offset={offset + limit} to see more)"
        )

    return [types.TextContent(type="text", text="\n".join(lines))]
