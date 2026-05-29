import asyncio
import sys

import yaml

from src.audio import OfflineAudioInput
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
audio_input = OfflineAudioInput(
    model_path=config["audio"]["model_path"],
    bin_path=config["audio"]["bin_path"],
)

SYSTEM_RUNNING = True
SHOULD_LISTEN = False


def handle_tray_toggle(listening_status):
    global SHOULD_LISTEN
    SHOULD_LISTEN = listening_status
    print(f"[System UI: Listening Mode Changed -> {SHOULD_LISTEN}]")


def handle_tray_exit():
    global SYSTEM_RUNNING
    SYSTEM_RUNNING = False
    print("[System UI: Initiating shutdown]")


tray = TrayManager(
    toggle_callback=handle_tray_toggle,
    exit_callback=handle_tray_exit,
    hotkey=config["hotkeys"]["toggle_listen"],
)


async def voice_assistant_loop():
    try:
        audio_input.validate()
    except FileNotFoundError as exc:
        print(f"[Setup error]\n{exc}", file=sys.stderr)
        await voice.speak(
            "Setup incomplete. Whisper binary or model file is missing, sir."
        )
        return

    await voice.speak(
        "Systems initialized and running in your taskbar background, sir. "
        "Press Control 1 to begin listening."
    )

    while SYSTEM_RUNNING:
        if SHOULD_LISTEN:
            user_text = await asyncio.to_thread(audio_input.listen_and_transcribe)
            if user_text:
                reply = brain.generate_response(
                    prompt=user_text,
                    system_instruction=config["assistant"]["system_prompt"],
                )
                if reply:
                    await voice.speak(reply)

        await asyncio.sleep(0.1)


if __name__ == "__main__":
    tray.start_background()

    try:
        asyncio.run(voice_assistant_loop())
    except KeyboardInterrupt:
        print("\nGoodbye.")
    sys.exit(0)
