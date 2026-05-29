import threading
import time

from PIL import Image, ImageDraw
import pystray
import keyboard

class TrayManager:
    def __init__(self, toggle_callback, exit_callback, hotkey="ctrl+1"):
        self.toggle_callback = toggle_callback
        self.exit_callback = exit_callback
        self.hotkey = hotkey
        self.icon = None
        self.is_listening = False
        self._last_toggle_at = 0.0

    def _create_icon_image(self, color="blue"):
        """Generates a simple neon circle icon dynamically (replicates Jarvis arc reactor look)."""
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        # Draw a glowing ring
        dc.ellipse([8, 8, 56, 56], outline=color, width=6)
        return image

    def _on_toggle(self, icon, item):
        now = time.monotonic()
        if now - self._last_toggle_at < 0.5:
            return
        self._last_toggle_at = now

        self.is_listening = not self.is_listening
        self.toggle_callback(self.is_listening)
        # Update tray icon color based on status
        new_color = "mic" if self.is_listening else "blue"
        # In a full app, you would swap image textures here

    def _on_exit(self, icon, item):
        self.icon.stop()
        self.exit_callback()

    def _setup_hotkeys(self):
        """Binds global keys using the configuration shortcut."""
        keyboard.add_hotkey(self.hotkey, lambda: self._on_toggle(None, None))

    def run(self):
        """Launches the system tray inside a secondary execution thread."""
        self._setup_hotkeys()
        
        menu = pystray.Menu(
            pystray.MenuItem("Toggle Listening (Ctrl+1)", self._on_toggle),
            pystray.MenuItem("Exit Jarvis", self._on_exit)
        )
        
        self.icon = pystray.Icon(
            "Jarvis", 
            self._create_icon_image("cyan"), 
            "Jarvis AI Assistant", 
            menu
        )
        
        # Run tray loop natively
        self.icon.run()

    def start_background(self):
        """Starts the tray helper without blocking your main python loop."""
        tray_thread = threading.Thread(target=self.run, daemon=True)
        tray_thread.start()