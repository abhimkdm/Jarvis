import asyncio
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from os_kernel.config_loader import resolve_active_config
from os_kernel.intent_router import IntentRouterLayer, normalize_track
from os_kernel.logs.log_config import get_jarvis_logger
from os_kernel.mcp.mcp_client_hub import MCPClientHub
from os_kernel.plugin.plugin_registry import PluginRegistry
from os_kernel.system_states import SystemStageManager
from os_kernel.tauri_bridge import TauriBridge
from os_kernel.temperature.system_states import SystemStateEngine
from drivers.audio import OfflineAudioInput
from drivers.llm import LLMManager, StateAwareLLMManager
from drivers.tts import TTSManager
from drivers.tray import TrayManager


class JarvisKernel:
    """Core engine: manages ears, voice, brain, plugins, agents, and MCP routing."""

    def __init__(self, config_path: str = "config.yaml"):
        self.console = Console()
        self.log = get_jarvis_logger()
        self.config = resolve_active_config(config_path)
        llm_boot = self.config.get("llm") or {}
        print(
            f"[Kernel Config: LLM profile={llm_boot.get('active_profile', 'local')} "
            f"provider={llm_boot.get('provider', 'ollama')} "
            f"requested={llm_boot.get('requested_environment', 'local')}"
            + (
                " (deployed unavailable — local fallback)"
                if llm_boot.get("fallback_used")
                else ""
            )
            + "]"
        )
        self.running = True
        self.should_listen = False

        assistant_cfg = self.config.get("assistant") or {}
        llm_cfg = self.config.get("llm") or {}
        self.stage_manager = SystemStageManager()
        self.llm_router = StateAwareLLMManager(
            llm_config=llm_cfg,
            stage_manager=self.stage_manager,
            base_url=self._ollama_v1_url(llm_cfg),
        )
        self.brain = LLMManager(
            llm_config=llm_cfg,
            system_prompt=assistant_cfg.get("system_prompt", ""),
            stage_manager=self.stage_manager,
            stage_orchestrator=self.llm_router,
        )
        self.intent_router = IntentRouterLayer(llm_config=llm_cfg)
        self.tauri_bridge = TauriBridge()
        self.voice = TTSManager(voice=self.config["tts"]["voice"])

        self.plugins = PluginRegistry()
        self.app_launcher = None
        self.mcp_hub = MCPClientHub()
        self.state_engine = SystemStateEngine()

        self.plugins.discover()
        self.app_launcher = self.plugins.app_launcher

        self.tray = TrayManager(
            toggle_callback=self._on_tray_toggle,
            exit_callback=self._on_tray_exit,
            hotkey=self.config["hotkeys"]["toggle_listen"],
        )

    def _on_tray_toggle(self, listening_status: bool) -> None:
        self.should_listen = listening_status
        print(f"[Kernel UI: Listening Mode Changed -> {self.should_listen}]")

    def _on_tray_exit(self) -> None:
        self.running = False
        print("[Kernel UI: Initiating shutdown]")

    @property
    def tauri_ipc(self) -> TauriBridge:
        """Alias for the Tauri/React IPC bridge used by the desktop shell."""
        return self.tauri_bridge

    @property
    def tts(self) -> TTSManager:
        """Alias for the voice synthesis driver."""
        return self.voice

    @staticmethod
    def _ollama_v1_url(llm_cfg: dict) -> str:
        root = str(
            llm_cfg.get("url") or llm_cfg.get("base_url", "http://localhost:11434")
        ).rstrip("/")
        return f"{root}/v1"

    async def _emit_active_tab(self, current_stage: str, parsed_payload: dict) -> None:
        await self.tauri_ipc.emit(
            "switch-active-tab",
            {"target_tab": current_stage},
        )
        await self.tauri_ipc.emit(
            "jarvis-focus-changed",
            {
                "active_tab": current_stage,
                "staged_context": parsed_payload,
            },
        )

    def _read_skills_handbook(self) -> str:
        """Reads the custom skills profile directly from disk."""
        skills_path = os.path.join(os.path.dirname(__file__), "skills", "skills.md")
        if os.path.exists(skills_path):
            with open(skills_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        return "I am a local microkernel assistant. My skills registry file is empty."

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

    @staticmethod
    def _merge_track_runtime(track: str, runtime_config: dict) -> dict:
        """Override state-engine temperature when the intent router selects a pipeline track."""
        track_overrides = {
            "TRACK_FILE_ANALYSIS": {
                "temperature": 0.2,
                "description": "File Analysis Pipeline (Intent Router)",
            },
            "TRACK_TMS": {
                "temperature": 0.0,
                "description": "Task Management Pipeline (Intent Router)",
            },
            "TRACK_BROWSER_AUTOMATION": {
                "temperature": 0.0,
                "description": "Browser Automation Pipeline (Intent Router)",
            },
            "TRACK_SYSTEM_COMMUNICATION": {
                "temperature": 0.0,
                "description": "Communication Pipeline (Outlook / Webex)",
            },
        }
        override = track_overrides.get(track)
        if not override:
            return runtime_config
        merged = dict(runtime_config)
        merged.update(override)
        return merged

    async def speak_and_update_ui(
        self, message: str, *, user_text: str | None = None
    ) -> None:
        await self.tauri_bridge.emit("jarvis-reply", {"text": message})
        await self.voice.speak(message)
        if user_text:
            memory = self.plugins.memory
            if memory:
                memory.update_memory(user_text, message)

    async def _run_llm_turn(
        self,
        query_text: str,
        tools: list,
        *,
        user_text: str,
        track: str,
        locked_stage: str | None = None,
        staged_context: dict | None = None,
    ) -> None:
        runtime_config = self._evaluate_runtime_config(query_text)
        runtime_config = self._merge_track_runtime(track, runtime_config)
        print(
            f"[Kernel Pipeline Track: {track} -> {runtime_config['description']} "
            f"(Temp: {runtime_config['temperature']})]"
        )

        ai_response = self.brain.generate_tool_aware_response(
            query_text,
            tools,
            temperature=runtime_config["temperature"],
            active_stage=locked_stage or track,
            staged_context=staged_context,
        )

        if ai_response.tool_calls:
            for call in ai_response.tool_calls:
                execution_reply = await self.mcp_hub.call_tool(
                    call.name, call.arguments
                )
                await self.speak_and_update_ui(execution_reply, user_text=user_text)
            return

        reply = ai_response.text or ""
        await self.speak_and_update_ui(reply, user_text=user_text)

    async def execute_standard_chat(
        self,
        user_text: str,
        clean_query: str | None = None,
        route: dict | None = None,
        *,
        locked_stage: str | None = None,
        staged_context: dict | None = None,
    ) -> None:
        query_text = clean_query or user_text
        track = normalize_track((route or {}).get("target", "TRACK_CONVERSATION"))
        await self._run_llm_turn(
            query_text,
            self.mcp_hub.tools_manifest,
            user_text=user_text,
            track=track,
            locked_stage=locked_stage,
            staged_context=staged_context,
        )

    async def execute_with_subset_tools(
        self,
        clean_query: str,
        route: dict,
        user_text: str,
        *,
        target_pool: str = "tms_server",
        locked_stage: str | None = None,
        staged_context: dict | None = None,
    ) -> None:
        tools = self.mcp_hub.tools_for_pool(target_pool)
        if not tools:
            print(
                f"[Kernel TMS: pool '{target_pool}' has no connected tools — "
                "falling back to standard chat]"
            )
            await self.execute_standard_chat(
                user_text,
                clean_query,
                route,
                locked_stage=locked_stage,
                staged_context=staged_context,
            )
            return

        await self._run_llm_turn(
            clean_query,
            tools,
            user_text=user_text,
            track="TRACK_TMS",
            locked_stage=locked_stage,
            staged_context=staged_context,
        )

    async def execute_silent_browser_task(
        self,
        action_query: str,
        *,
        user_text: str,
        locked_stage: str | None = None,
        staged_context: dict | None = None,
    ) -> None:
        route = {
            "normalized_query": action_query,
            "extracted_parameters": (staged_context or {}).get("meta", {}),
            "locked_stage": locked_stage,
            "staged_context": staged_context,
        }
        await self.execute_browser_automation(route, user_text)

    async def execute_browser_automation(self, route: dict, user_text: str) -> None:
        params = route.get("extracted_parameters") or {}
        print(f"[Kernel Browser Automation: params={params}]")
        reply = (
            "Sir, the Playwright browser automation workers are not yet mounted "
            "in this kernel build."
        )
        await self.speak_and_update_ui(reply, user_text=user_text)

    async def execute_tms_task(
        self,
        action_query: str,
        *,
        user_text: str,
        locked_stage: str | None = None,
        staged_context: dict | None = None,
    ) -> None:
        route = {
            "normalized_query": action_query,
            "target": "TRACK_TMS",
            "extracted_parameters": (staged_context or {}).get("meta", {}),
            "locked_stage": locked_stage,
            "staged_context": staged_context,
        }
        await self.execute_with_subset_tools(
            action_query,
            route,
            user_text,
            target_pool="tms_server",
            locked_stage=locked_stage,
            staged_context=staged_context,
        )

    @staticmethod
    def _paths_from_routing(route: dict) -> list[Path]:
        params = route.get("extracted_parameters") or {}
        paths: list[Path] = []
        for key in ("path", "file", "filepath", "target_file"):
            value = params.get(key)
            if value:
                paths.append(Path(str(value)))
        for key in ("paths", "files"):
            values = params.get(key)
            if isinstance(values, list):
                paths.extend(Path(str(item)) for item in values)
        return paths

    @staticmethod
    def _read_file_snapshot(path: Path, max_chars: int = 12000) -> str:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return f"[unreadable: {exc}]"
        if len(text) > max_chars:
            return text[:max_chars] + "\n... [truncated]"
        return text

    async def execute_file_diff_agent(
        self,
        route: dict,
        user_text: str,
        *,
        locked_stage: str | None = None,
        staged_context: dict | None = None,
    ) -> None:
        clean_query = route.get("normalized_query") or user_text
        paths = self._paths_from_routing(route)

        if paths:
            blocks = []
            for path in paths[:3]:
                blocks.append(f"### {path}\n{self._read_file_snapshot(path)}")
            query_text = (
                f"{clean_query}\n\n--- File snapshot context ---\n" + "\n\n".join(blocks)
            )
        else:
            query_text = clean_query

        await self._run_llm_turn(
            query_text,
            self.mcp_hub.tools_manifest,
            user_text=user_text,
            track="TRACK_FILE_ANALYSIS",
            locked_stage=locked_stage,
            staged_context=staged_context,
        )

    async def execute_communication_task(
        self,
        action_query: str,
        *,
        user_text: str,
        locked_stage: str | None = None,
        staged_context: dict | None = None,
    ) -> None:
        route = {
            "normalized_query": action_query,
            "target": "TRACK_SYSTEM_COMMUNICATION",
            "extracted_parameters": (staged_context or {}).get("meta", {}),
            "locked_stage": locked_stage,
            "staged_context": staged_context,
        }
        tools = self.mcp_hub.tools_for_pool("outlook_server")
        if tools:
            await self._run_llm_turn(
                action_query,
                tools,
                user_text=user_text,
                track="TRACK_SYSTEM_COMMUNICATION",
                locked_stage=locked_stage,
                staged_context=staged_context,
            )
            return
        await self.execute_standard_chat(
            user_text,
            action_query,
            route=route,
            locked_stage=locked_stage,
            staged_context=staged_context,
        )

    async def on_command_received(self, raw_voice_text: str) -> None:
        """State-aware routing layer: latch stage, parse payload, emit UI tab, execute track."""
        # 1. Standardize and check strings through phonetic dictionaries
        active_stage, action_query = self.stage_manager.clean_and_evaluate(
            raw_voice_text
        )

        # TERMINATION INTERCEPT (runs locally before LLM processing)
        if active_stage == "TRACK_TERMINATE":
            print(
                f"\n[Kernel] Termination sequence caught from input: "
                f"'{raw_voice_text}'"
            )
            print(
                "[Kernel] Disconnecting local hardware hooks and exiting process..."
            )
            self.running = False

            if hasattr(self, "tts") and self.tts:
                await self.tts.speak("Goodbye, sir.")

            await self.tauri_bridge.emit(
                "system-will-exit",
                {"status": "shutdown"},
            )

            await asyncio.sleep(1.2)
            sys.exit(0)

        # 2. Not a stop phrase — proceed to standard LLM routing track
        llm_payload = self.llm_router.process_staged_query(raw_voice_text)
        current_stage = llm_payload.get("active_stage", active_stage)
        action_query = llm_payload.get("action_query", action_query)

        print(
            f"[Kernel on_command_received: stage={current_stage} "
            f"action={action_query!r} meta={llm_payload.get('meta', {})}]"
        )

        await self._emit_active_tab(current_stage, llm_payload)

        llm_kwargs = {
            "locked_stage": current_stage,
            "staged_context": llm_payload,
        }

        if current_stage == "TRACK_BROWSER_AUTOMATION":
            await self.execute_silent_browser_task(
                action_query, user_text=raw_voice_text, **llm_kwargs
            )
        elif current_stage == "TRACK_TMS":
            await self.execute_tms_task(
                action_query, user_text=raw_voice_text, **llm_kwargs
            )
        elif current_stage == "TRACK_FILE_ANALYSIS":
            route = {
                "normalized_query": action_query,
                "extracted_parameters": llm_payload.get("meta", {}),
                **llm_kwargs,
            }
            await self.execute_file_diff_agent(route, raw_voice_text, **llm_kwargs)
        elif current_stage == "TRACK_SYSTEM_COMMUNICATION":
            await self.execute_communication_task(
                action_query, user_text=raw_voice_text, **llm_kwargs
            )
        elif current_stage == "TRACK_SYSTEM_UTILITY":
            if self.app_launcher:
                utility_reply = self.app_launcher.execute(action_query)
                if utility_reply:
                    await self.speak_and_update_ui(
                        utility_reply, user_text=raw_voice_text
                    )
                    return
            await self.speak_and_update_ui(
                "I could not map that utility command, sir.",
                user_text=raw_voice_text,
            )
        else:
            await self.execute_standard_chat(
                raw_voice_text,
                action_query,
                route={"target": current_stage, "staged_context": llm_payload},
                **llm_kwargs,
            )

    async def process_user_input(self, user_text: str) -> None:
        try:
            if self._is_skills_inquiry(user_text):
                handbook_text = self._read_skills_handbook()
                await self.voice.speak(handbook_text)
                return

            llm_context = {"messages": []}
            self.plugins.inject_context(user_text, llm_context)

            if self.app_launcher:
                local_intercept = self.app_launcher.execute(user_text)
                if local_intercept:
                    await self.speak_and_update_ui(local_intercept, user_text=user_text)
                    return

            await self.on_command_received(user_text)
        except Exception:
            self.log.exception("Failed to process user input")

    @staticmethod
    def _mcp_server_display_name(filename: str) -> str:
        labels = {
            "apps_server.py": "System-Apps-Server",
            "notepad_server.py": "Notepad-Server",
            "outlook_server.py": "Outlook-Server",
        }
        stem = os.path.splitext(filename)[0].replace("_", "-").title()
        return labels.get(filename, stem)

    @staticmethod
    def _mcp_status_style(status: str) -> str:
        styles = {
            "CONNECTED": "bold green",
            "CONNECTING": "bold yellow",
            "FAILED": "bold red",
        }
        return styles.get(status, "white")

    def _build_mcp_registry_table(self) -> Table:
        table = Table(
            title="Model Context Protocol (MCP) Active Subsystems",
            title_style="bold magenta",
        )
        table.add_column("Subsystem Worker", style="cyan", no_wrap=True)
        table.add_column("Transport Protocol", style="green")
        table.add_column("Status Gating", style="bold green")

        for file_path in self.mcp_hub.discover_server_files():
            filename = os.path.basename(file_path)
            info = self.mcp_hub.server_status.get(filename, {"status": "PENDING"})
            status = info["status"]
            if status == "CONNECTED" and info.get("latency_ms") is not None:
                status_text = f"CONNECTED [{info['latency_ms']:.1f}ms]"
            else:
                status_text = status

            table.add_row(
                self._mcp_server_display_name(filename),
                "STDIO (JSON-RPC 2.0)",
                f"[{self._mcp_status_style(status)}]{status_text}[/{self._mcp_status_style(status)}]",
            )
        return table

    async def boot_up(self) -> None:
        """Initializes the core system microkernel and displays an executive dashboard."""
        os.system("cls" if os.name == "nt" else "clear")

        llm_cfg = self.config.get("llm") or {}
        llm_model = llm_cfg.get("model", "unknown")
        active = llm_cfg.get("active_profile", "local")
        provider = llm_cfg.get("provider", "ollama")
        fallback = llm_cfg.get("fallback_used", False)
        profile_line = f"`{active}` ({provider})"
        if fallback:
            profile_line += " — deployed unreachable, using local fallback"

        welcome_markdown = f"""
# JARVIS: COGNITIVE OPERATING SYSTEM
---
* **System Kernel Status:** `ONLINE`
* **LLM Profile:** {profile_line}
* **Model:** `{llm_model}`
* **Speech-to-Text Driver:** Local Bare-Metal `whisper.cpp`
* **Audio / MCP / Plugins:** Local on device
        """

        self.console.print(
            Panel(
                Markdown(welcome_markdown),
                title="[bold cyan]Microkernel Core Initialization[/bold cyan]",
                border_style="cyan",
            )
        )

        table = self._build_mcp_registry_table()
        connect_task = asyncio.create_task(self.mcp_hub.connect_servers())

        with Live(table, console=self.console, refresh_per_second=4) as live:
            while not connect_task.done():
                live.update(self._build_mcp_registry_table())
                await asyncio.sleep(0.25)
            await connect_task
            live.update(self._build_mcp_registry_table())

        self.console.print(
            "\n[bold green]Jarvis Kernel loaded with dynamic runtime tuning, sir. "
            "Keyboard override active.[/bold green]"
        )
        hotkey = self.config["hotkeys"]["toggle_listen"].replace("+", " + ").upper()
        self.console.print(
            f"[bold white]Press {hotkey} to begin listening.[/bold white]\n"
        )

        self.tray.start_background()
        await self.run()

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

        manual_input = self.plugins.manual_input

        try:
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
        finally:
            await self.mcp_hub.shutdown()
