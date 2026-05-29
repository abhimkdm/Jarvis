import msvcrt
import time

class ManualInputPlugin:
    def __init__(self):
        pass

    def execute(self, user_text, context=None):
        """
        This layer runs BEFORE speech recognition. 
        If context contains a manual override, it passes it along.
        """
        # If text was intercepted by our manual input check, we return it as the text
        if context is not None and context.get("manual_text"):
            return context["manual_text"]
        return None

    def check_for_keyboard_override(self):
        """
        Checks if the user pressed 't' to type a manual command.
        Non-blocking check for Windows.
        """
        print("[System: Press 'T' to TYPE a command instead of speaking... (2s window)]")
        
        start_time = time.time()
        while time.time() - start_time < 2:
            if msvcrt.kbhit():
                key = msvcrt.getch().decode('utf-8').lower()
                if key == 't':
                    print("\n⌨️  [Manual Override Activated]")
                    typed_command = input("Type your command for Jarvis, sir: ").strip()
                    if typed_command:
                        return typed_command
            time.sleep(0.1)
        return None