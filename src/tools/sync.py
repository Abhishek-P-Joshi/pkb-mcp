from pathlib import Path
import mcp.types as types
from src.config import config
from src.connectors.file_parser import FileParser
from src.connectors.hasher import hash_file
from src.pipeline.ingest import pipeline

SYNC_TOOL = types.Tool(
    name="sync_knowledge_base",
    description=(
        "Manually trigger a sync of all connected sources (inbox folder, "
        "Obsidian vault if configured, YouTube playlist). Skips files that haven't changed."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "enum": ["all", "inbox", "obsidian", "youtube"],
                "description": "Which source to sync. Defaults to 'all'.",
            },
            "playlist_id": {
                "type": "string",
                "description": (
                    "YouTube playlist ID. 'WL' = Watch Later (default), "
                    "'LL' = Liked Videos, or any playlist ID from the URL."
                ),
            },
        },
        "required": [],
    },
)

YOUTUBE_SYNC_TOOL = types.Tool(
    name="sync_youtube_playlist",
    description=(
        "Sync a YouTube playlist into the knowledge base. "
        "Fetches full metadata (title, channel, duration, views, upload date) "
        "for each video. Skips already-ingested videos. "
        "Defaults to Watch Later (WL). Use playlist_id='LL' for Liked Videos "
        "or paste any YouTube playlist ID."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "playlist_id": {
                "type": "string",
                "description": "YouTube playlist ID. Defaults to 'WL' (Watch Later).",
            },
            "fetch_full_metadata": {
                "type": "boolean",
                "description": (
                    "Fetch full metadata per video (slower but richer). "
                    "Set false for a quick title-only import."
                ),
                "default": True,
            },
            "playlist_name": {
                "type": "string",
                "description": "Friendly name for the source e.g. 'saved' or 'watchlater_backup'. Used to identify videos from this playlist in browse and search.",
            },
        },
        "required": [],
    },
)

_parser = FileParser()
_supported = {".md", ".txt", ".docx"}


async def handle_sync(arguments: dict) -> list[types.TextContent]:
    source = arguments.get("source", "all")

    # ── YouTube ──────────────────────────────────────────────────────────────
    if source == "youtube":
        return await handle_youtube_sync(arguments)

    inbox_synced = inbox_skipped = 0
    obsidian_synced = obsidian_skipped = obsidian_errors = 0
    obsidian_status = "disabled"

    # ── Inbox ────────────────────────────────────────────────────────────────
    if source in ("all", "inbox"):
        inbox_path = config.storage_path / "watched" / "inbox"
        inbox_path.mkdir(parents=True, exist_ok=True)

        for file_path in inbox_path.rglob("*"):
            if file_path.is_dir() or file_path.suffix.lower() not in _supported:
                continue
            parsed = _parser.parse(str(file_path))
            if parsed.get("error"):
                continue
            file_hash = hash_file(str(file_path))
            note_id = "inbox_" + file_path.stem
            result = pipeline.ingest(
                text=parsed["text"],
                source="inbox",
                note_id=note_id,
                file_hash=file_hash,
            )
            if result["status"] == "skipped":
                inbox_skipped += 1
            else:
                inbox_synced += 1

    # ── Obsidian ─────────────────────────────────────────────────────────────
    if source in ("all", "obsidian"):
        vault_path = config.obsidian_vault_path
        if vault_path and Path(vault_path).exists():
            from src.connectors.obsidian import ObsidianConnector
            connector = ObsidianConnector(vault_path)
            result = connector.sync()
            obsidian_synced = result["synced"]
            obsidian_skipped = result["skipped"]
            obsidian_errors = len(result["errors"])
            obsidian_status = (
                f"{obsidian_synced} synced, {obsidian_skipped} skipped"
                + (f", {obsidian_errors} errors" if obsidian_errors else "")
            )
        elif vault_path:
            obsidian_status = f"path not found: {vault_path}"

    # ── Summary ──────────────────────────────────────────────────────────────
    lines = ["Sync complete"]
    if source in ("all", "inbox"):
        lines.append(f"  inbox:    {inbox_synced} synced, {inbox_skipped} skipped")
    if source in ("all", "obsidian"):
        lines.append(f"  obsidian: {obsidian_status}")

    return [types.TextContent(type="text", text="\n".join(lines))]


async def handle_youtube_sync(arguments: dict) -> list[types.TextContent]:
    playlist_id = arguments.get("playlist_id", "WL")
    fetch_full_metadata = bool(arguments.get("fetch_full_metadata", True))
    playlist_name = arguments.get("playlist_name") or None

    try:
        from src.connectors.youtube_api import sync_playlist
        result = sync_playlist(
            playlist_id=playlist_id,
            fetch_full_metadata=fetch_full_metadata,
            playlist_name=playlist_name,
        )
        lines = [
            f"YouTube sync complete (playlist: {playlist_id})",
            f"  Synced:  {result['synced']}",
            f"  Skipped: {result['skipped']}",
            f"  Errors:  {result['errors']}",
        ]
        return [types.TextContent(type="text", text="\n".join(lines))]
    except FileNotFoundError as e:
        return [types.TextContent(type="text", text=f"YouTube auth error:\n{e}")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"YouTube sync failed: {e}")]
