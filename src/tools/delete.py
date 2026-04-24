import mcp.types as types
from src.store import storage

# ── delete_item ──────────────────────────────────────────────────

DELETE_TOOL = types.Tool(
    name="delete_item",
    description="""Remove a note or video from the knowledge base.
Soft delete (default) marks the item as deleted but keeps the data
so it can be restored. Hard delete permanently removes it from both
SQLite and ChromaDB — use with caution.

Use note_id to delete one specific item.
Use source to bulk-delete everything from a source.
Bulk deletes require confirm_bulk=true as a safety guard.
Use hard=true only when you are sure you never need the data again.""",
    inputSchema={
        "type": "object",
        "properties": {
            "note_id": {
                "type": "string",
                "description": "ID of the specific note to delete"
            },
            "source": {
                "type": "string",
                "description": "Delete all notes from this source e.g. 'manual', 'obsidian'"
            },
            "hard": {
                "type": "boolean",
                "default": False,
                "description": "If true, permanently deletes. If false (default), soft deletes (recoverable)."
            },
            "confirm_bulk": {
                "type": "boolean",
                "default": False,
                "description": "Must be true to confirm bulk deletion by source"
            },
            "deleted_from": {
                "type": "string",
                "default": "user",
                "description": "Reason for deletion: 'user', 'playlist_removed', 'file_deleted'"
            }
        },
        "required": []
    }
)


async def handle_delete(arguments: dict) -> list[types.TextContent]:
    note_id = arguments.get("note_id")
    source = arguments.get("source")
    hard = arguments.get("hard", False)
    confirm_bulk = arguments.get("confirm_bulk", False)
    deleted_from = arguments.get("deleted_from", "user")
    delete_type = "permanently deleted" if hard else "soft deleted (recoverable)"

    # Validate — must have note_id or source
    if not note_id and not source:
        return [types.TextContent(type="text",
            text="Error: provide either note_id or source.")]

    # Single note delete
    if note_id:
        note = storage.fts.get_by_id(note_id)
        if not note:
            return [types.TextContent(type="text",
                text=f"Note not found: {note_id}")]
        title = note.get("title", note_id)
        if hard:
            storage.fts.hard_delete(note_id)
            storage.vector.delete_by_note_id(note_id)
        else:
            storage.fts.soft_delete(note_id, deleted_from)
            storage.vector.delete_by_note_id(note_id)
        return [types.TextContent(type="text",
            text=f"{delete_type.capitalize()}: {title}\n"
                 f"  note_id: {note_id}\n"
                 + ("  Use restore_item to undo." if not hard else
                    "  This cannot be undone."))]

    # Bulk delete by source — require confirmation
    if source and not confirm_bulk:
        count = storage.fts.count_notes(source=source)
        return [types.TextContent(type="text",
            text=f"This will {('permanently delete' if hard else 'soft delete')} "
                 f"{count} notes from source '{source}'.\n"
                 f"Call again with confirm_bulk=true to proceed.")]

    if source and confirm_bulk:
        notes = storage.fts.list_notes(source=source, limit=10000)
        count = len(notes)
        for note in notes:
            nid = note["id"]
            if hard:
                storage.fts.hard_delete(nid)
                storage.vector.delete_by_note_id(nid)
            else:
                storage.fts.soft_delete(nid, deleted_from)
                storage.vector.delete_by_note_id(nid)
        action = "Permanently deleted" if hard else "Soft deleted"
        undo = "" if hard else "\nUse restore_item with source to undo."
        return [types.TextContent(type="text",
            text=f"{action} {count} notes from source '{source}'.{undo}")]


# ── restore_item ──────────────────────────────────────────────────

RESTORE_TOOL = types.Tool(
    name="restore_item",
    description="""Restore a soft-deleted note back to active status.
Only works on soft-deleted items — hard-deleted items cannot be restored.
Use list_deleted to see what can be restored.""",
    inputSchema={
        "type": "object",
        "properties": {
            "note_id": {
                "type": "string",
                "description": "ID of the note to restore"
            },
            "source": {
                "type": "string",
                "description": "Restore all soft-deleted notes from this source"
            }
        },
        "required": []
    }
)


async def handle_restore(arguments: dict) -> list[types.TextContent]:
    note_id = arguments.get("note_id")
    source = arguments.get("source")

    if not note_id and not source:
        return [types.TextContent(type="text",
            text="Error: provide either note_id or source.")]

    if note_id:
        from src.pipeline.ingest import pipeline
        storage.fts.restore(note_id)
        note = storage.fts.get_by_id(note_id)
        if note and note.get("raw_text"):
            pipeline.ingest(
                text=note["raw_text"],
                source=note["source"],
                note_id=note_id,
                file_hash=None,  # bypass dedup — force re-embed
            )
            return [types.TextContent(type="text",
                text=f"Restored: {note.get('title', note_id)}\n"
                     f"  Re-indexed in semantic search.\n"
                     f"  note_id: {note_id}")]
        else:
            return [types.TextContent(type="text",
                text=f"Restored in database but raw_text missing — "
                     f"FTS search works, semantic search unavailable.\n"
                     f"Re-ingest the original file to fix semantic search.")]

    if source:
        from src.pipeline.ingest import pipeline
        deleted = storage.fts.list_deleted(source=source, limit=10000)
        restored = 0
        for note in deleted:
            nid = note["id"]
            storage.fts.restore(nid)
            full = storage.fts.get_by_id(nid)  # fetch raw_text — list_deleted omits it
            if full and full.get("raw_text"):
                pipeline.ingest(
                    text=full["raw_text"],
                    source=full["source"],
                    note_id=nid,
                    file_hash=None,  # bypass dedup — force re-embed
                )
            restored += 1
        return [types.TextContent(type="text",
            text=f"Restored {restored} notes from source '{source}'.\n"
                 f"All re-indexed in semantic search.")]


# ── list_deleted ──────────────────────────────────────────────────

LIST_DELETED_TOOL = types.Tool(
    name="list_deleted",
    description="""Browse soft-deleted notes. Shows what has been deleted
and can be restored. Use restore_item to bring items back.
Hard-deleted items do not appear here.""",
    inputSchema={
        "type": "object",
        "properties": {
            "content_type": {
                "type": "string",
                "enum": ["video", "article", "note", "list", "doc"]
            },
            "source": {"type": "string"},
            "deleted_after": {
                "type": "string",
                "description": "ISO date YYYY-MM-DD — show items deleted after this date"
            },
            "limit": {"type": "integer", "default": 20},
            "offset": {"type": "integer", "default": 0}
        },
        "required": []
    }
)


async def handle_list_deleted(arguments: dict) -> list[types.TextContent]:
    results = storage.fts.list_deleted(
        content_type=arguments.get("content_type"),
        source=arguments.get("source"),
        deleted_after=arguments.get("deleted_after"),
        limit=arguments.get("limit", 20),
        offset=arguments.get("offset", 0),
    )

    if not results:
        return [types.TextContent(type="text",
            text="No soft-deleted items found.")]

    lines = [f"Found {len(results)} soft-deleted items:\n"]
    for r in results:
        lines.append(f"• {r.get('title', 'Untitled')}")
        lines.append(f"  id: {r['id']}")
        lines.append(f"  type: {r.get('content_type')} | "
                     f"source: {r.get('source')}")
        lines.append(f"  deleted: {str(r.get('deleted_at',''))[:16]} "
                     f"({r.get('deleted_from', 'user')})")
        lines.append("")

    lines.append("Use restore_item(note_id=...) to restore any of these.")
    return [types.TextContent(type="text", text="\n".join(lines))]
