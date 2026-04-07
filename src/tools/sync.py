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
        "Obsidian vault if configured). Skips files that haven't changed."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "enum": ["all", "inbox", "obsidian"],
                "description": "Which source to sync. Defaults to 'all'.",
            }
        },
        "required": [],
    },
)

_parser = FileParser()
_supported = {".md", ".txt", ".docx"}


async def handle_sync(arguments: dict) -> list[types.TextContent]:
    source = arguments.get("source", "all")

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
