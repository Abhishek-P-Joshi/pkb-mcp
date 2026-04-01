import mcp.types as types
from datetime import datetime
from src.config import config

async def handle_health_check() -> list[types.TextContent]:
    status = {
        "status": "ok",
        "server": "pkb-mcp",
        "version": "0.1.0",
        "env": config.env,
        "transport": config.transport,
        "storage_path": str(config.storage_path),
        "timestamp": datetime.now().isoformat(),
    }
    lines = [f"{k}: {v}" for k, v in status.items()]
    return [types.TextContent(type="text", text="\n".join(lines))]
