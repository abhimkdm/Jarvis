import subprocess

class AppLauncherPlugin:
    def __init__(self):
        self.app_map = {
            "chrome": "start chrome",
            "browser": "start chrome",
            "notepad": "notepad.exe",
            "calculator": "calc.exe",
            "explorer": "explorer.exe",
        }

    def execute(self, user_text, context=None):
        """Processes text. Returns a vocal response string if executed, else None."""
        # Layer A passes context for memory injection only — don't launch twice.
        if context is not None:
            return None

        cleaned = user_text.lower()
        if "open" in cleaned or "launch" in cleaned:
            for app_name, command in self.app_map.items():
                if app_name in cleaned:
                    subprocess.Popen(command, shell=True)
                    return f"Opening {app_name} right away, sir."
        return None