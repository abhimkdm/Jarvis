import asyncio
import sys

import yaml

from os_kernel.log_config import get_jarvis_logger
from os_kernel.mcp_server import MCPServer
from os_kernel.plugin_registry import PluginRegistry
from drivers.audio import OfflineAudioInput
from drivers.llm import LLMManager
from drivers.tts import TTSManager
from drivers.tray import TrayManager


class JarvisKernel:
    """Core engine: manages ears, voice, brain, plugins, agents, and MCP routing."""

    def __init__(self, config_path: str = "config.yaml"):
        self.log = get_jarvis_logger()
        self.config = self._load_config(config_path)
        self.running = True
        self.should_listen = False

        self.brain = LLMManager(
            base_url=self.config["llm"]["url"],
            model=self.config["llm"]["model"],
        )
        self.voice = TTSManager(voice=self.config["tts"]["voice"])

        self.plugins = PluginRegistry()
        self.mcp = MCPServer()

        self.plugins.discover()

        self.tray = TrayManager(
            toggle_callback=self._on_tray_toggle,
            exit_callback=self._on_tray_exit,
            hotkey=self.config["hotkeys"]["toggle_listen"],
        )

    @staticmethod
    def _load_config(config_path: str) -> dict:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _on_tray_toggle(self, listening_status: bool) -> None:
        self.should_listen = listening_status
        print(f"[Kernel UI: Listening Mode Changed -> {self.should_listen}]")

    def _on_tray_exit(self) -> None:
        self.running = False
        print("[Kernel UI: Initiating shutdown]")

    async def process_user_input(self, user_text: str) -> None:
        try:
            if "exit" in user_text.lower() or "shutdown" in user_text.lower():
                self.running = False
                await self.voice.speak("Powering down.")
                return

            llm_context = {"messages": []}
            self.plugins.inject_context(user_text, llm_context)

            command_reply = self.plugins.try_intercept(user_text)
            if command_reply:
                await self.voice.speak(command_reply)
                return

            command_reply = self.mcp.route_and_parse(user_text)
            if command_reply:
                await self.voice.speak(command_reply)
                return

            payload = [
                {"role": "system", "content": self.config["assistant"]["system_prompt"]}
            ]
            payload.extend(llm_context["messages"])
            payload.append({"role": "user", "content": user_text})

            reply = self.brain.generate_response(payload)

            memory = self.plugins.memory
            if memory:
                memory.update_memory(user_text, reply)

            await self.voice.speak(reply)
        except Exception:
            self.log.exception("Failed to process user input")

    async def run(self) -> None:
        audio_engine = OfflineAudioInput(
            model_path=self.config["audio"]["model_path"],
            bin_path=self.config["audio"]["bin_path"],
        )

        try:
            audio_engine.validate()
        except FileNotFoundError as exc:
            self.log.error("Audio setup failed: %s", exc)
            print(f"[Setup error]\n{exc}", file=sys.stderr)
            await self.voice.speak(
                "Setup incomplete. Whisper binary or model file is missing, sir."
            )
            return

        await self.voice.speak(
            "Systems online. Microkernel initialized. Keyboard override active. "
            "Press Control 1 to begin listening."
        )

        manual_input = self.plugins.manual_input

        while self.running:
            if self.should_listen:
                user_text = None

                if manual_input:
                    user_text = await asyncio.to_thread(
                        manual_input.check_for_keyboard_override
                    )

                if not user_text:
                    user_text = await asyncio.to_thread(
                        audio_engine.listen_and_transcribe
                    )
                else:
                    print(f"You (Typed): {user_text}")

                if user_text:
                    await self.process_user_input(user_text)
                    if not self.running:
                        break

            await asyncio.sleep(0.1)
