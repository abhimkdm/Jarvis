import importlib
import pkgutil

from os_kernel.log_config import get_agent_logger, get_mcp_logger


class MCPServer:
    def __init__(self):
        self.protocols = []  # List of registered MCP structural objects
        self.agents = {}  # Cached directory dictionary mapping name -> Agent Class
        self.log = get_mcp_logger("server")

        self._load_agents()
        self._load_mcp_protocols()

    def _load_agents(self):
        """Indexes the autonomous background execution workers."""
        print("\n[Kernel OS: Registering Worker Agent Fleet...]")
        import agents

        for _, module_name, is_pkg in pkgutil.iter_modules(agents.__path__):
            mod = importlib.import_module(f"agents.{module_name}")
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if isinstance(attr, type) and attr_name.endswith("Agent"):
                    agent_key = module_name.replace("_agent", "")
                    self.agents[agent_key] = attr()
                    print(f" -> Worker Spawned & Registered: [{agent_key}]")

    def _load_mcp_protocols(self):
        """Indexes the communication protocol routing definitions."""
        print("\n[Kernel OS: Loading Model Context Protocol (MCP) Schemas...]")
        import mcp

        for _, module_name, is_pkg in pkgutil.iter_modules(mcp.__path__):
            # Check for structural python modules within package path
            if not is_pkg and module_name != "__init__":
                mod = importlib.import_module(f"mcp.{module_name}")
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if isinstance(attr, type) and attr_name.endswith("MCP"):
                        self.protocols.append(attr())
                        print(f" -> Protocol Blueprint Mounted: {attr_name}")

    def route_and_parse(self, user_text):
        """Routes parsed protocol tokens directly to their target agent workers."""
        try:
            for protocol in self.protocols:
                intent_data = protocol.match_and_parse(user_text)

                if intent_data:  # Found a matching input schema!
                    target_name = intent_data["agent"]
                    payload = intent_data["payload"]

                    if not payload:
                        return (
                            f"I matched the request to the {target_name} agent, "
                            "but found no text payload to transmit."
                        )

                    worker_agent = self.agents.get(target_name)
                    if worker_agent:
                        print(
                            f"[Kernel OS: Executing Agent pipeline logic -> "
                            f"{target_name}]"
                        )
                        agent_log = get_agent_logger(target_name)
                        try:
                            return worker_agent.run(payload)
                        except Exception:
                            agent_log.exception(
                                "Agent %s failed while running", target_name
                            )
                            self.log.exception(
                                "Agent pipeline failed for %s", target_name
                            )
                            return (
                                f"The {target_name} agent encountered an error. "
                                "Check logs/Agents for details."
                            )
                    else:
                        self.log.error(
                            "Protocol matched '%s' but agent is not installed",
                            target_name,
                        )
                        return (
                            f"Protocol matched to '{target_name}', "
                            "but that corresponding agent is uninstalled."
                        )

            return None
        except Exception:
            self.log.exception("MCP routing failed")
            return None
