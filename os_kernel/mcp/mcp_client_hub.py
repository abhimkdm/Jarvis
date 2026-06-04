import os
import glob
import asyncio
import sys
import traceback

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from os_kernel.logs.log_config import get_mcp_logger


def _format_traceback_lines(exc: BaseException | None) -> list[str]:
    """
    Safely flattens an exception traceback context into a list of
    strings for clean log dumping.
    """
    if not exc:
        return []

    raw_traceback_str = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    return raw_traceback_str.rstrip().splitlines()


def _format_exception_detail(exc: BaseException) -> str:
    """Expand TaskGroup / ExceptionGroup wrappers into readable sub-exception lines."""
    lines: list[str] = []

    def walk(err: BaseException, indent: int = 0) -> None:
        pad = "  " * indent
        lines.append(f"{pad}{type(err).__name__}: {err}")
        if isinstance(err, BaseExceptionGroup):
            for index, sub in enumerate(err.exceptions):
                lines.append(f"{pad}  sub-exception [{index}]:")
                walk(sub, indent + 2)
            return
        if err.__cause__ is not None:
            lines.append(f"{pad}  caused by:")
            walk(err.__cause__, indent + 1)
        elif err.__context__ is not None and not err.__suppress_context__:
            lines.append(f"{pad}  context:")
            walk(err.__context__, indent + 1)

    walk(exc)
    lines.append("")
    lines.extend(_format_traceback_lines(exc))
    return "\n".join(lines)


def _is_cancelled(exc: BaseException) -> bool:
    if isinstance(exc, asyncio.CancelledError):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return bool(exc.exceptions) and all(
            _is_cancelled(sub) for sub in exc.exceptions
        )
    return False


def _log_mcp_failure(file_path: str, exc: BaseException) -> None:
    server_label = os.path.basename(file_path)
    stem = os.path.splitext(server_label)[0]
    logger = get_mcp_logger(stem)
    detail = _format_exception_detail(exc)
    print(f" └─ [MCP ERROR] {server_label}:")
    for line in detail.splitlines():
        print(f"    {line}")
    logger.error("MCP server session failed (%s):\n%s", server_label, detail)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

TOOL_POOLS: dict[str, frozenset[str]] = {
    "tms_server": frozenset({"tms_server.py"}),
    "apps_server": frozenset({"apps_server.py"}),
    "outlook_server": frozenset({"outlook_server.py"}),
    "notepad_server": frozenset({"notepad_server.py"}),
}


class MCPClientHub:
    def __init__(self):
        self.sessions = []
        self.tools_manifest = []
        self._server_tasks = []
        self._shutdown_event = asyncio.Event()
        self.server_status: dict[str, dict] = {}

    @staticmethod
    def discover_server_files() -> list[str]:
        return sorted(
            glob.glob(os.path.join(PROJECT_ROOT, "mcp_servers", "*_server.py"))
        )

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
        server_files = self.discover_server_files()

        if not server_files:
            get_mcp_logger("hub").warning(
                "No server scripts discovered in mcp_servers/"
            )
            return

        tasks = []
        for file_path in server_files:
            server_label = os.path.basename(file_path)
            self.server_status[server_label] = {"status": "CONNECTING", "latency_ms": None}
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

    async def _manage_server_session(self, file_path, params):
        server_label = os.path.basename(file_path)
        started_at = asyncio.get_running_loop().time()
        try:
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    self.sessions.append(session)

                    response = await session.list_tools()
                    latency_ms = (asyncio.get_running_loop().time() - started_at) * 1000
                    self.server_status[server_label] = {
                        "status": "CONNECTED",
                        "latency_ms": latency_ms,
                        "tool_count": len(response.tools),
                    }
                    for tool in response.tools:
                        self.tools_manifest.append({
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.inputSchema,
                            "server": server_label,
                        })

                    await self._shutdown_event.wait()
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            self.server_status[server_label] = {"status": "FAILED", "latency_ms": None}
            _log_mcp_failure(file_path, exc)

    async def shutdown(self):
        """Release MCP subprocess sessions before the event loop closes."""
        self._shutdown_event.set()
        for task in self._server_tasks:
            task.cancel()
        if self._server_tasks:
            results = await asyncio.gather(
                *self._server_tasks, return_exceptions=True
            )
            for task, result in zip(self._server_tasks, results):
                if isinstance(result, BaseException) and not _is_cancelled(result):
                    server_file = task.get_name().removeprefix("mcp:")
                    _log_mcp_failure(
                        os.path.join(PROJECT_ROOT, "mcp_servers", server_file),
                        result,
                    )
        self._server_tasks.clear()
        self.sessions.clear()
        self.server_status.clear()

    def tools_for_pool(self, target_pool: str) -> list[dict]:
        allowed = TOOL_POOLS.get(target_pool)
        if allowed is None:
            return list(self.tools_manifest)
        return [
            tool
            for tool in self.tools_manifest
            if tool.get("server") in allowed
        ]

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