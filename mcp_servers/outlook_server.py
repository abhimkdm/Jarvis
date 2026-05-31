import os
import sys

# ─── SYS PATH PATCH: Forces the background subprocess to see your root workspace ───
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
from mcp.server.fastmcp import FastMCP
from agents.outlook_agent import OutlookAgent

server = FastMCP("Outlook-Server")
worker = OutlookAgent()

# ... keep your remaining outlook @server.tool definitions exactly the same ...

if __name__ == "__main__":
    server.run(transport="stdio")