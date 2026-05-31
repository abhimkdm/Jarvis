import os
import glob
import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class MCPClientHub:
    def __init__(self):
        self.sessions = []
        self.tools_manifest = []
        self._server_tasks = []
        self._shutdown_event = asyncio.Event()

    def _server_env(self):
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            PROJECT_ROOT
            if not existing
            else f"{PROJECT_ROOT}{os.pathsep}{existing}"
        )
        return env

    async def connect_servers(self):
        print("\n[Kernel OS: Accessing Official Model Context Protocol Subsystems...]")
        server_files = sorted(
            set(
                glob.glob(os.path.join(PROJECT_ROOT, "mcp_servers", "*_mcp.py"))
                + glob.glob(os.path.join(PROJECT_ROOT, "mcp_servers", "*_server.py"))
            )
        )

        if not server_files:
            print(" └─ [CRITICAL WARNING]: No server scripts discovered in mcp_servers/")
            return

        tasks = []
        for file_path in server_files:
            print(f" └─ Spawning Standard Protocol Stream for: {file_path}")
            server_params = StdioServerParameters(
                command=sys.executable,
                args=[file_path],
                env=self._server_env(),
                cwd=PROJECT_ROOT,
            )
            tasks.append(
                asyncio.create_task(
                    self._manage_server_session(file_path, server_params),
                    name=f"mcp:{os.path.basename(file_path)}",
                )
            )

        self._server_tasks = tasks

        retries = 0
        while len(self.sessions) < len(server_files) and retries < 10:
            await asyncio.sleep(0.5)
            retries += 1

        failed = len(server_files) - len(self.sessions)
        if failed:
            print(
                f" └─ [WARNING]: {failed} MCP server(s) failed to mount. "
                "Check logs/ and ensure dependencies (e.g. pywin32) are installed."
            )

        print(
            f"[Kernel OS: All {len(self.sessions)} active protocol tunnels securely mounted.]\n"
        )

    async def _manage_server_session(self, file_path, params):
        try:
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

                    await self._shutdown_event.wait()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f" └─ [MCP ERROR] {os.path.basename(file_path)}: {exc}")

    async def shutdown(self):
        """Release MCP subprocess sessions before the event loop closes."""
        self._shutdown_event.set()
        for task in self._server_tasks:
            task.cancel()
        if self._server_tasks:
            await asyncio.gather(*self._server_tasks, return_exceptions=True)
        self._server_tasks.clear()
        self.sessions.clear()

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