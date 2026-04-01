from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.lowlevel.server import NotificationOptions
import mcp.server.stdio
import mcp.types as types
from src.config import config
from rich.console import Console

console = Console()
server = Server("pkb-mcp")

# ── Tools are registered here as we build them ──────────────────────────────
# Each phase will add imports and @server.call_tool() handlers below.
# For now we have the health check tool only (see tools/health.py).

from src.tools.health import handle_health_check
from src.tools.ingest import handle_ingest_content, INGEST_TOOL

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="health_check",
            description="Check that the PKB MCP server is running and responsive.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        INGEST_TOOL,
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "health_check":
        return await handle_health_check()
    elif name == "ingest_content":
        return await handle_ingest_content(arguments)
    raise ValueError(f"Unknown tool: {name}")


async def run():
    console.print(f"[bold green]PKB MCP server starting[/bold green]")
    console.print(f"  env:       {config.env}")
    console.print(f"  transport: {config.transport}")
    console.print(f"  storage:   {config.storage_path}")

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
