import asyncio
import os
import re
import sys
import tempfile
from datetime import datetime

import edge_tts
import pygame
import speech_recognition as sr
from openai import OpenAI

# Local Ollama client
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)

WAKE_PHRASE = "hey jarvis"
CHAT_LOG_FILE = "chat_history.txt"
EXIT_RE = re.compile(
    r"\b(exit|quit|stop|goodbye|good\s*bye|bye|shutdown|shut\s*down)\b",
    re.IGNORECASE,
)
TTS_VOICE = "en-US-BrianNeural"
LISTEN_TIMEOUT_SEC = 5
PHRASE_LIMIT_SEC = 12

recognizer = sr.Recognizer()
recognizer.dynamic_energy_threshold = True

_pygame_ready = False


def init_audio() -> None:
    global _pygame_ready
    if not _pygame_ready:
        pygame.mixer.init()
        _pygame_ready = True


def play_audio(path: str) -> None:
    """Play audio in-process (no external media player window on Windows)."""
    init_audio()
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    clock = pygame.time.Clock()
    while pygame.mixer.music.get_busy():
        clock.tick(10)


def log_exchange(user_text: str, assistant_text: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(CHAT_LOG_FILE, "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}]\n")
        log.write(f"You: {user_text}\n")
        log.write(f"Jarvis: {assistant_text}\n\n")


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def contains_wake_word(text: str) -> bool:
    return WAKE_PHRASE in normalize(text)


def is_exit_command(text: str) -> bool:
    """True if the user wants to quit (works with or without the wake phrase)."""
    return bool(EXIT_RE.search(normalize(text)))


def extract_command(text: str) -> str:
    """Return text after 'hey jarvis', or empty string if only the wake phrase was said."""
    match = re.search(r"hey\s+jarvis", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return text[match.end() :].strip(" ,.!?")


async def speak(text: str) -> None:
    print(f"Jarvis: {text}")
    communicate = edge_tts.Communicate(text, TTS_VOICE)

    fd, audio_path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        await communicate.save(audio_path)
        await asyncio.to_thread(play_audio, audio_path)
    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass


def listen(prompt: str = "[Listening...]") -> str | None:
    with sr.Microphone() as source:
        print(prompt)
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        try:
            audio = recognizer.listen(
                source,
                timeout=LISTEN_TIMEOUT_SEC,
                phrase_time_limit=PHRASE_LIMIT_SEC,
            )
        except sr.WaitTimeoutError:
            return None

    try:
        text = recognizer.recognize_google(audio).strip()
        if text:
            print(f"You: {text}")
        return text or None
    except sr.UnknownValueError:
        return None
    except sr.RequestError:
        print("[System Error: Check network connection for speech recognition]")
        return None


def ask_llama(prompt: str) -> str:
    response = client.chat.completions.create(
        model="llama3.2:1b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are Jarvis, a helpful voice assistant. "
                    "Keep replies conversational and brief: one or two sentences only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content.strip()


async def wait_for_wake_word() -> tuple[str | None, bool]:
    """
    Block until the user says 'Hey Jarvis', then return (command, exit_requested).
    Exit phrases are honored even without the wake word.
    """
    while True:
        heard = listen("[Waiting for 'Hey Jarvis'...]")
        if not heard:
            continue
        if is_exit_command(heard):
            return None, True
        if not contains_wake_word(heard):
            continue

        command = extract_command(heard)
        if command:
            if is_exit_command(command):
                return None, True
            return command, False

        follow_up = listen("[Yes?]")
        if follow_up and is_exit_command(follow_up):
            return None, True
        return follow_up, False


async def main() -> None:
    try:
        with sr.Microphone():
            pass
    except OSError as exc:
        print(f"No microphone available: {exc}", file=sys.stderr)
        sys.exit(1)

    await speak("System online. Say Hey Jarvis when you need me.")

    while True:
        user_input, should_exit = await wait_for_wake_word()
        if should_exit:
            await speak("Goodbye.")
            break
        if not user_input:
            continue

        try:
            reply = ask_llama(user_input)
        except Exception as exc:
            print(f"[Ollama error: {exc}]")
            await speak("I could not reach the language model. Is Ollama running?")
            continue

        log_exchange(user_input, reply)
        await speak(reply)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye.")
