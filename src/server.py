from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.lowlevel.server import NotificationOptions
import mcp.server.stdio
import mcp.types as types
from src.config import config
from src.connectors.watcher import FolderWatcher
from rich.console import Console

console = Console(stderr=True)
server = Server("pkb-mcp")

# ── Tools are registered here as we build them ──────────────────────────────
# Each phase will add imports and @server.call_tool() handlers below.
# For now we have the health check tool only (see tools/health.py).

from src.tools.health import handle_health_check
from src.tools.ingest import handle_ingest_content, INGEST_TOOL
from src.tools.sync import handle_sync, handle_youtube_sync, SYNC_TOOL, YOUTUBE_SYNC_TOOL
from src.tools.search import handle_search, SEARCH_TOOL
from src.tools.list_items import handle_list, LIST_TOOL
from src.tools.answer import handle_answer, ANSWER_TOOL
from src.tools.browse import handle_browse, BROWSE_TOOL
from src.tools.delete import (
    DELETE_TOOL, handle_delete,
    RESTORE_TOOL, handle_restore,
    LIST_DELETED_TOOL, handle_list_deleted,
)

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="health_check",
            description="Check that the PKB MCP server is running and responsive.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        INGEST_TOOL,
        SYNC_TOOL,
        YOUTUBE_SYNC_TOOL,
        SEARCH_TOOL,
        LIST_TOOL,
        ANSWER_TOOL,
        BROWSE_TOOL,
        DELETE_TOOL,
        RESTORE_TOOL,
        LIST_DELETED_TOOL,
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "health_check":
        return await handle_health_check()
    elif name == "ingest_content":
        return await handle_ingest_content(arguments)
    elif name == "sync_knowledge_base":
        return await handle_sync(arguments)
    elif name == "sync_youtube_playlist":
        return await handle_youtube_sync(arguments)
    elif name == "search_knowledge":
        return await handle_search(arguments)
    elif name == "list_items":
        return await handle_list(arguments)
    elif name == "answer_question":
        return await handle_answer(arguments)
    elif name == "browse_knowledge":
        return await handle_browse(arguments)
    elif name == "delete_item":
        return await handle_delete(arguments)
    elif name == "restore_item":
        return await handle_restore(arguments)
    elif name == "list_deleted":
        return await handle_list_deleted(arguments)
    raise ValueError(f"Unknown tool: {name}")


def start_watcher() -> FolderWatcher:
    inbox_path = config.storage_path / "watched" / "inbox"
    inbox_path.mkdir(parents=True, exist_ok=True)
    watcher = FolderWatcher(str(inbox_path))
    watcher.start()
    return watcher


async def run():
    console.print(f"[bold green]PKB MCP server starting[/bold green]")
    console.print(f"  env:       {config.env}")
    console.print(f"  transport: {config.transport}")
    console.print(f"  storage:   {config.storage_path}")

    _watcher = start_watcher()
    console.print(f"  watcher:   {config.storage_path / 'watched' / 'inbox'}")

    from src.scheduler import start_scheduler
    _scheduler = start_scheduler()

    if config.transport == "stdio":
        # Local mode — Claude desktop spawns this process directly
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="pkb-mcp",
                    server_version="0.1.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )

    # NOTE[remote]: uncomment this block when switching to HTTP transport
    # elif config.transport == "http":
    #     from fastapi import FastAPI
    #     from fastapi.middleware.cors import CORSMiddleware
    #     import uvicorn
    #     from src.auth import get_auth_middleware
    #
    #     app = FastAPI(title="PKB MCP Server")
    #     middleware = get_auth_middleware()
    #     if middleware:
    #         app.middleware("http")(middleware)
    #     app.mount("/mcp", server.streamable_http_app())
    #
    #     console.print(f"  host:      {config.host}:{config.port}")
    #     uvicorn.run(app, host=config.host, port=config.port)
