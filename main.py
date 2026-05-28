import asyncio
import os
import re
import sys
from datetime import datetime

import edge_tts
import pygame
import speech_recognition as sr
from openai import OpenAI

# Ollama client
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)

# Pygame mixer — no external media player windows on Windows
pygame.mixer.init()
recognizer = sr.Recognizer()
recognizer.dynamic_energy_threshold = True

WAKE_PHRASE = "hey jarvis"
CHAT_LOG_FILE = "chat_history.txt"
TTS_VOICE = "en-US-BrianNeural"
AUDIO_FILE = "response.mp3"
EXIT_RE = re.compile(
    r"\b(exit|quit|stop|goodbye|good\s*bye|bye|shutdown|shut\s*down)\b",
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def contains_wake_word(text: str) -> bool:
    return WAKE_PHRASE in normalize(text)


def is_exit_command(text: str) -> bool:
    return bool(EXIT_RE.search(normalize(text)))


def extract_command(text: str) -> str:
    match = re.search(r"hey\s+jarvis", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return text[match.end() :].strip(" ,.!?")


def log_exchange(user_text: str, assistant_text: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(CHAT_LOG_FILE, "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}]\n")
        log.write(f"You: {user_text}\n")
        log.write(f"Jarvis: {assistant_text}\n\n")


async def speak(text: str) -> None:
    """Convert text to speech and play in-process (no popup windows)."""
    print(f"Jarvis: {text}")
    communicate = edge_tts.Communicate(text, TTS_VOICE)
    await communicate.save(AUDIO_FILE)

    pygame.mixer.music.load(AUDIO_FILE)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        await asyncio.sleep(0.1)

    pygame.mixer.music.unload()
    try:
        os.remove(AUDIO_FILE)
    except OSError:
        pass


def listen(prompt: str = "\n[Jarvis is listening...]") -> str | None:
    with sr.Microphone() as source:
        print(prompt)
        recognizer.adjust_for_ambient_noise(source, duration=0.8)
        try:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
        except sr.WaitTimeoutError:
            return None

    try:
        print("[Thinking...]")
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
    try:
        response = client.chat.completions.create(
            model="llama3.2:1b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Jarvis, a brilliant, helpful, and witty AI assistant. "
                        "Keep responses conversational, concise (1-3 sentences max), and sharp."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        return (
            "I encountered an error connecting to my brain. "
            f"Make sure Ollama is running. Error: {exc}"
        )


async def wait_for_wake_word() -> tuple[str | None, bool]:
    """Wait for 'Hey Jarvis', then return (command, should_exit)."""
    while True:
        heard = listen("\n[Waiting for 'Hey Jarvis'...]")
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

        follow_up = listen("\n[Yes, sir?]")
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

    await speak("Systems initialized. I am online and ready, sir. Say Hey Jarvis when you need me.")

    while True:
        user_input, should_exit = await wait_for_wake_word()
        if should_exit:
            await speak("Understood. Powering down systems. Goodbye.")
            break
        if not user_input:
            await asyncio.sleep(0.1)
            continue

        reply = ask_llama(user_input)
        log_exchange(user_input, reply)
        await speak(reply)
        await asyncio.sleep(0.1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye.")
