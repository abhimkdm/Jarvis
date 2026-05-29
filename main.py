import asyncio
import importlib
import pkgutil
import sys

import yaml

from src.llm import LLMManager
from src.tts import TTSManager
from src.tray import TrayManager

with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

brain = LLMManager(
    base_url=config["llm"]["url"],
    model=config["llm"]["model"],
)
voice = TTSManager(voice=config["tts"]["voice"])

PLUGINS = []
memory_plugin = None
manual_input_plugin = None

SYSTEM_RUNNING = True
SHOULD_LISTEN = False


def discover_plugins():
    global memory_plugin, manual_input_plugin
    import plugins

    print("\n[System OS: Indexing decentralized features...]")

    for _, module_name, is_pkg in pkgutil.iter_modules(plugins.__path__):
        if not is_pkg:
            continue

        mod = importlib.import_module(f"plugins.{module_name}")

        for attribute_name in dir(mod):
            attribute = getattr(mod, attribute_name)
            if isinstance(attribute, type) and attribute_name.endswith("Plugin"):
                plugin_instance = attribute()
                PLUGINS.append(plugin_instance)
                print(f" -> Successfully mounted plugin: {attribute_name}")

                if attribute_name == "ChatMemoryPlugin":
                    memory_plugin = plugin_instance
                elif attribute_name == "ManualInputPlugin":
                    manual_input_plugin = plugin_instance


def handle_tray_toggle(listening_status):
    global SHOULD_LISTEN
    SHOULD_LISTEN = listening_status
    print(f"[System UI: Listening Mode Changed -> {SHOULD_LISTEN}]")


def handle_tray_exit():
    global SYSTEM_RUNNING
    SYSTEM_RUNNING = False
    print("[System UI: Initiating shutdown]")


discover_plugins()

tray = TrayManager(
    toggle_callback=handle_tray_toggle,
    exit_callback=handle_tray_exit,
    hotkey=config["hotkeys"]["toggle_listen"],
)


async def process_user_input(user_text: str) -> None:
    if "exit" in user_text.lower() or "shutdown" in user_text.lower():
        global SYSTEM_RUNNING
        SYSTEM_RUNNING = False
        await voice.speak("Powering down.")
        return

    llm_context = {"messages": []}
    for plugin in PLUGINS:
        plugin.execute(user_text, context=llm_context)

    for plugin in PLUGINS:
        command_reply = plugin.execute(user_text)
        if command_reply:
            await voice.speak(command_reply)
            return

    payload = [{"role": "system", "content": config["assistant"]["system_prompt"]}]
    payload.extend(llm_context["messages"])
    payload.append({"role": "user", "content": user_text})

    reply = brain.generate_response(payload)

    if memory_plugin:
        memory_plugin.update_memory(user_text, reply)

    await voice.speak(reply)


async def main_loop():
    from src.audio import OfflineAudioInput

    audio_engine = OfflineAudioInput(
        model_path=config["audio"]["model_path"],
        bin_path=config["audio"]["bin_path"],
    )

    try:
        audio_engine.validate()
    except FileNotFoundError as exc:
        print(f"[Setup error]\n{exc}", file=sys.stderr)
        await voice.speak(
            "Setup incomplete. Whisper binary or model file is missing, sir."
        )
        return

    await voice.speak(
        "Systems fully decentralized. Keyboard override active. "
        "Press Control 1 to begin listening."
    )

    while SYSTEM_RUNNING:
        if SHOULD_LISTEN:
            user_text = None

            if manual_input_plugin:
                user_text = await asyncio.to_thread(
                    manual_input_plugin.check_for_keyboard_override
                )

            if not user_text:
                user_text = await asyncio.to_thread(
                    audio_engine.listen_and_transcribe
                )
            else:
                print(f"You (Typed): {user_text}")

            if user_text:
                await process_user_input(user_text)
                if not SYSTEM_RUNNING:
                    break

        await asyncio.sleep(0.1)


if __name__ == "__main__":
    tray.start_background()
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("\nGoodbye.")
    sys.exit(0)
