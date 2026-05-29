class MCPServer:
    """Routes commands to MCP tool integrations registered with the kernel."""

    def __init__(self):
        self.tools: dict[str, object] = {}

    def register_tool(self, name: str, handler) -> None:
        self.tools[name] = handler
        print(f" -> Registered MCP tool: {name}")

    async def route(self, user_text: str) -> str | None:
        for name, handler in self.tools.items():
            matcher = getattr(handler, "matches", None)
            if matcher and not matcher(user_text):
                continue

            invoke = getattr(handler, "invoke", handler)
            result = invoke(user_text)
            if hasattr(result, "__await__"):
                result = await result
            if result is not None:
                return result
        return None
