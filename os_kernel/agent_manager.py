class AgentManager:
    """Manages autonomous agent subsystems and routes work to them before LLM fallback."""

    def __init__(self):
        self.agents: list = []

    def register(self, agent) -> None:
        self.agents.append(agent)
        print(f" -> Registered agent: {type(agent).__name__}")

    async def route(self, user_text: str) -> str | None:
        for agent in self.agents:
            handler = getattr(agent, "handle", None)
            if handler is None:
                continue
            result = handler(user_text)
            if hasattr(result, "__await__"):
                result = await result
            if result is not None:
                return result
        return None
