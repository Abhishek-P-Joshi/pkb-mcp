import mcp.types as types
from src.pipeline.ingest import IngestPipeline

# Instantiated once at module load so the embedding model loads only once
pipeline = IngestPipeline()

INGEST_TOOL = types.Tool(
    name="ingest_content",
    description=(
        "Add a note, document, or URL to the knowledge base. "
        "Automatically detects content type, enriches URLs, "
        "chunks and embeds the content."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The full text content to ingest",
            },
            "source": {
                "type": "string",
                "description": "Where this came from: obsidian, apple_notes, onedrive, manual",
            },
            "note_id": {
                "type": "string",
                "description": "Optional stable ID for this note (for updates)",
            },
            "file_hash": {
                "type": "string",
                "description": "Optional MD5 hash of file for deduplication",
            },
        },
        "required": ["text", "source"],
    },
)


async def handle_ingest_content(arguments: dict) -> list[types.TextContent]:
    text = arguments.get("text")
    source = arguments.get("source")

    if not text or not source:
        raise ValueError("'text' and 'source' are required arguments")

    result = pipeline.ingest(
        text=text,
        source=source,
        note_id=arguments.get("note_id"),
        file_hash=arguments.get("file_hash"),
    )

    if result["status"] == "skipped":
        message = f"Skipped: {result['reason']}"
    else:
        message = (
            f"Ingested successfully.\n"
            f"  note_id:      {result['note_id']}\n"
            f"  content_type: {result['content_type']}\n"
            f"  chunks:       {result['chunks']}\n"
            f"  title:        {result['title']}"
        )

    return [types.TextContent(type="text", text=message)]
