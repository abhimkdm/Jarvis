import importlib
import pkgutil


class AppLauncherPlugin:
    def __init__(self):
        self.commands = self._load_commands()

    @staticmethod
    def _load_commands():
        import plugins.app_launcher.commands as commands_pkg

        loaded = []
        for _, module_name, _ in pkgutil.iter_modules(commands_pkg.__path__):
            mod = importlib.import_module(f"plugins.app_launcher.commands.{module_name}")
            if hasattr(mod, "MATCH") and hasattr(mod, "exec_command"):
                loaded.append(mod)
        return loaded

    def execute(self, user_text, context=None):
        """Processes text. Returns a vocal response string if executed, else None."""
        # Layer A passes context for memory injection only — don't launch twice.
        if context is not None:
            return None

        cleaned = user_text.lower()
        for command in self.commands:
            if any(phrase in cleaned for phrase in command.MATCH):
                return command.exec_command()
        return None
