import subprocess
import time

import pyautogui

from os_kernel.log_config import get_agent_logger


class NotepadAgent:
    def __init__(self):
        self.log = get_agent_logger("notepad")

    def run(self, text_payload):
        """Pure operational task processor."""
        try:
            print("[Agent Fleet: Initializing Notepad subprocess shell...]")
            subprocess.Popen("notepad.exe", shell=True)
            time.sleep(0.8)  # Wait for UI context focus

            print("[Agent Fleet: Writing data array to interface...]")
            pyautogui.write(text_payload, interval=0.01)
            return "I have successfully launched notepad and typed your message, sir."
        except Exception:
            self.log.exception("Notepad agent failed")
            return "Agent operational error. Check logs/Agents for details."
