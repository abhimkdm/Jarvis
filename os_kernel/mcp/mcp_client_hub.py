import os
import glob
import asyncio
import sys
# Python will now successfully fetch these from the official pip package!
from mcp import ClientSession, StdioServerParameters 
from mcp.client.stdio import stdio_client

class MCPClientHub:
    def __init__(self):
        self.sessions = []
        self.tools_manifest = [] 

    async def connect_servers(self):
        print("\n[Kernel OS: Accessing Official Model Context Protocol Subsystems...]")
        
        # ─── UPDATED: Pointing to mcp_servers/ instead of mcp/ ───
        server_files = glob.glob(os.path.join("mcp_servers", "*_server.py"))
        
        for file_path in server_files:
            print(f" └─ Spawning Standard Protocol Stream for: {file_path}")
            
            server_params = StdioServerParameters(
                command=sys.executable,
                args=[file_path],
                env=os.environ.copy()
            )
            
            asyncio.create_task(self._manage_server_session(server_params))
            
        await asyncio.sleep(1.5)

    async def _manage_server_session(self, params):
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                self.sessions.append(session)
                
                response = await session.list_tools()
                for tool in response.tools:
                    self.tools_manifest.append({
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.input_schema
                    })
                    print(f"    ├── Standard Tool Compiled: [{tool.name}]")
                    
                while True:
                    await asyncio.sleep(1)

    async def call_tool(self, tool_name, arguments):
        """Sends a JSON-RPC execution request with loose string tolerance."""
        target_tool = tool_name.strip().lower().replace("_", "").replace(" ", "")

        for session in self.sessions:
            try:
                response = await session.list_tools()

                for tool in response.tools:
                    server_tool_clean = tool.name.lower().replace("_", "").replace(" ", "")

                    if target_tool == server_tool_clean:
                        print(
                            f"[Client Hub: Exact match found! Mapping '{tool_name}' -> '{tool.name}']"
                        )
                        result = await session.call_tool(tool.name, arguments)
                        return result.content[0].text
            except Exception as e:
                print(f"[Client Hub Error on session communication: {e}]")
                continue

        return f"Error: Tool '{tool_name}' could not be executed on any live MCP server."