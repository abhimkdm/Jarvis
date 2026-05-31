import asyncio
import os
import re

import edge_tts
import pygame


class TTSManager:
    def __init__(self, voice="en-US-BrianNeural"):
        self.voice = voice
        pygame.mixer.init()

    def _clean_text_for_speech(self, text: str) -> str:
        """
        Strips all structural markdown symbols, headers, and bullet points
        so the text reads like a natural, fluid sentence.
        """
        cleaned = re.sub(r"#+\s*", "", text)
        cleaned = re.sub(r"^[ \t]*[*+-][ \t]+", "", cleaned, flags=re.MULTILINE)
        cleaned = cleaned.replace("**", "").replace("*", "").replace("__", "").replace("_", "")
        cleaned = cleaned.replace("(", ", ").replace(")", "")
        cleaned = re.sub(r" +", " ", cleaned)
        return cleaned.strip()

    async def speak(self, raw_text: str) -> None:
        if not raw_text:
            return

        vocal_text = self._clean_text_for_speech(raw_text)
        print(f"Jarvis: {vocal_text}")

        communicate = edge_tts.Communicate(vocal_text, self.voice)
        audio_file = "temp_response.mp3"

        await communicate.save(audio_file)

        pygame.mixer.music.load(audio_file)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.1)

        pygame.mixer.music.unload()
        try:
            os.remove(audio_file)
        except OSError:
            pass