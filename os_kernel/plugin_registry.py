import importlib
import pkgutil


class PluginRegistry:
    """Discovers, mounts, and routes commands through decentralized feature plugins."""

    def __init__(self):
        self.plugins: list = []
        self._named: dict[str, object] = {}

    def discover(self) -> None:
        import plugins

        print("\n[Kernel: Indexing decentralized features...]")

        for _, module_name, is_pkg in pkgutil.iter_modules(plugins.__path__):
            if not is_pkg:
                continue

            mod = importlib.import_module(f"plugins.{module_name}")

            for attribute_name in dir(mod):
                attribute = getattr(mod, attribute_name)
                if isinstance(attribute, type) and attribute_name.endswith("Plugin"):
                    plugin_instance = attribute()
                    self.plugins.append(plugin_instance)
                    self._named[attribute_name] = plugin_instance
                    print(f" -> Successfully mounted plugin: {attribute_name}")

    def get(self, name: str):
        return self._named.get(name)

    @property
    def memory(self):
        return self._named.get("ChatMemoryPlugin")

    @property
    def manual_input(self):
        return self._named.get("ManualInputPlugin")

    def inject_context(self, user_text: str, context: dict) -> None:
        for plugin in self.plugins:
            plugin.execute(user_text, context=context)

    def try_intercept(self, user_text: str) -> str | None:
        for plugin in self.plugins:
            reply = plugin.execute(user_text)
            if reply:
                return reply
        return None
