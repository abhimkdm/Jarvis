import asyncio
import edge_tts
import pygame
import os

class TTSManager:
    def __init__(self, voice="en-US-BrianNeural"):
        self.voice = voice
        pygame.mixer.init()

    async def speak(self, text):
        print(f"Jarvis: {text}")
        communicate = edge_tts.Communicate(text, self.voice)
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