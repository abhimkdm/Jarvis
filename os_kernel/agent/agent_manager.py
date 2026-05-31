from os_kernel.logs.log_config import get_agent_logger


class AgentManager:
    """Manages autonomous agent subsystems in the worker fleet."""

    def __init__(self):
        self.agents: dict[str, object] = {}
        self.log = get_agent_logger("manager")

    def register(self, name: str, agent) -> None:
        self.agents[name] = agent
        print(f" -> Registered agent: {name}")

    def run(self, name: str, payload: str) -> str | None:
        agent = self.agents.get(name)
        if agent is None:
            return None

        runner = getattr(agent, "run", None)
        if runner is None:
            self.log.error("Agent %s has no run() method", name)
            return None

        agent_log = get_agent_logger(name)
        try:
            return runner(payload)
        except Exception:
            agent_log.exception("Agent %s run failed", name)
            return None

    async def route(self, user_text: str) -> str | None:
        """Legacy handle-based routing for agents without MCP delegation."""
        for agent in self.agents.values():
            handler = getattr(agent, "handle", None)
            if handler is None:
                continue
            try:
                result = handler(user_text)
                if hasattr(result, "__await__"):
                    result = await result
                if result is not None:
                    return result
            except Exception:
                self.log.exception("Legacy agent handler failed")
        return None
