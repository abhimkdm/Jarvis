import asyncio
import os
import sys

import yaml

from os_kernel.logs.log_config import get_jarvis_logger
from os_kernel.mcp.mcp_client_hub import MCPClientHub
from os_kernel.plugin.plugin_registry import PluginRegistry
from os_kernel.temperature.system_states import SystemStateEngine
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
        self.mcp_hub = MCPClientHub()
        self.state_engine = SystemStateEngine()
        self.active_capabilities_prompt = ""

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

    def _read_skills_handbook(self) -> str:
        """Reads the custom skills profile directly from disk."""
        skills_path = os.path.join(os.path.dirname(__file__), "skills", "skills.md")
        if os.path.exists(skills_path):
            with open(skills_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        return "I am a local microkernel assistant. My skills registry file is empty."

    def _generate_skills_manifest(self) -> str:
        """Inspect registries and create a strict capability list for the LLM."""
        manifest = f"\n\n{self._read_skills_handbook()}\n"

        manifest += (
            "\n=== ACTIVE SYSTEM CAPABILITIES (YOU CAN ONLY DO THESE REMOTELY) ===\n"
        )

        manifest += "Official MCP Tools (LLM function-calling):\n"
        for tool in self.mcp_hub.tools_manifest:
            description = tool.get("description") or "No description provided."
            manifest += f" - {tool['name']}: {description}\n"

        manifest += "Background Extensions and Features:\n"
        for plugin in self.plugins.plugins:
            plugin_name = plugin.__class__.__name__
            manifest += f" - {plugin_name} (Active in memory context loop)\n"

        manifest += "=================================================================\n"
        return manifest

    @staticmethod
    def _is_skills_inquiry(user_text: str) -> bool:
        cleaned = user_text.lower()
        return any(
            phrase in cleaned
            for phrase in (
                "what can you do",
                "what are your skills",
                "what all you can do",
            )
        )

    def _evaluate_runtime_config(self, user_text: str) -> dict:
        """Dynamic parameter calculator — scales LLM temperature from intent and MCP state."""
        mcp_active = any(
            getattr(session, "awaiting_confirmation", False)
            for session in self.mcp_hub.sessions
        )
        runtime_config = self.state_engine.evaluate_runtime_parameters(
            user_text,
            is_mcp_awaiting=mcp_active,
        )
        print(
            f"[Kernel State Matrix: Shifting to {runtime_config['description']} "
            f"(Temp: {runtime_config['temperature']})]"
        )
        return runtime_config

    async def process_user_input(self, user_text: str) -> None:
        try:
            if "exit" in user_text.lower() or "shutdown" in user_text.lower():
                self.running = False
                await self.voice.speak("Powering down.")
                return

            if self._is_skills_inquiry(user_text):
                handbook_text = self._read_skills_handbook()
                await self.voice.speak(handbook_text)
                return

            llm_context = {"messages": []}
            self.plugins.inject_context(user_text, llm_context)

            command_reply = self.plugins.try_intercept(user_text)
            if command_reply:
                await self.voice.speak(command_reply)
                return

            runtime_config = self._evaluate_runtime_config(user_text)
            target_temp = runtime_config["temperature"]

            ai_response = self.brain.generate_tool_aware_response(
                user_text,
                self.mcp_hub.tools_manifest,
                temperature=target_temp,
            )

            if ai_response.tool_calls:
                for call in ai_response.tool_calls:
                    execution_reply = await self.mcp_hub.call_tool(
                        call.name, call.arguments
                    )
                    await self.voice.speak(execution_reply)

                memory = self.plugins.memory
                if memory:
                    memory.update_memory(user_text, execution_reply)
                return

            reply = ai_response.text

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

        await self.mcp_hub.connect_servers()
        self.active_capabilities_prompt = self._generate_skills_manifest()
        print(self.active_capabilities_prompt)

        await self.voice.speak(
            "Kernel loaded with dynamic runtime tuning, sir. "
            "Keyboard override active. Press Control 1 to begin listening."
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
