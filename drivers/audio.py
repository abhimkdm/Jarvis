import audioop
import os
import subprocess
import time
import wave

import numpy as np
import speech_recognition as sr
from scipy.signal import butter, lfilter

from os_kernel.log_config import get_jarvis_logger

WHISPER_CANDIDATES = (
    "whisper_bin/whisper-cli.exe",
    "whisper_bin/main.exe",
)

SAMPLE_RATE = 16000
WIN_DLL_NOT_FOUND = 3221225781

WHISPER_ARTIFACTS = {
    "[blank]",
    "[blank_audio]",
    "blank_audio",
    "[music]",
    "[silence]",
    "you",
    "thank you.",
    "thank you for watching.",
    "subtitles by amara.org",
}

WHISPER_ARTIFACT_PREFIXES = (
    "[blank",
    "[music",
    "[silence",
    "(blank",
)


class OfflineAudioInput:
    """Offline microphone input using whisper.cpp with DSP noise cancellation."""

    def __init__(
        self,
        model_path: str = "models/ggml-tiny.en.bin",
        bin_path: str = "whisper_bin/whisper-cli.exe",
        temp_wav: str = "temp_clean.wav",
    ):
        self.model_path = model_path
        self.bin_path = bin_path
        self.temp_wav = temp_wav
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300
        self._resolved_bin: str | None = None
        self._ambient_calibrated = False
        self.sample_rate = SAMPLE_RATE
        self.log = get_jarvis_logger()

    def resolve_bin_path(self) -> str:
        """Pick the first available whisper.cpp CLI binary."""
        if self._resolved_bin and os.path.isfile(self._resolved_bin):
            return self._resolved_bin

        candidates = [self.bin_path, *WHISPER_CANDIDATES]
        seen: set[str] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            if os.path.isfile(candidate):
                self._resolved_bin = os.path.abspath(candidate)
                return self._resolved_bin

        raise FileNotFoundError(
            "No whisper.cpp binary found. Place one of these in whisper_bin/:\n"
            "  - whisper-cli.exe (recommended)\n"
            "  - main.exe (deprecated)\n"
            "Download whisper-bin-x64.zip from "
            "https://github.com/ggml-org/whisper.cpp/releases"
        )

    def validate(self) -> None:
        """Raise FileNotFoundError if whisper binary or model is missing."""
        bin_path = self.resolve_bin_path()
        if bin_path.endswith("main.exe"):
            print(
                "[Warning: main.exe is deprecated. Use whisper-cli.exe instead.]"
            )

        bin_dir = os.path.dirname(bin_path)
        required_dlls = ("ggml.dll", "ggml-base.dll", "ggml-cpu.dll")
        missing = [
            dll for dll in required_dlls
            if not os.path.isfile(os.path.join(bin_dir, dll))
        ]
        if missing:
            raise FileNotFoundError(
                "Whisper setup incomplete in whisper_bin/. Missing DLLs:\n"
                f"  {', '.join(missing)}\n"
                "Download the full whisper-bin-x64.zip release and extract "
                "all files into whisper_bin/."
            )

        if not os.path.isfile(self.model_path):
            raise FileNotFoundError(
                f"Whisper model not found: {self.model_path}\n"
                "Download ggml-tiny.en.bin into the models/ folder."
            )

    @staticmethod
    def _butter_bandpass(lowcut: float, highcut: float, fs: int, order: int = 4):
        """Generates coefficients for an 80 Hz–8 kHz voice bandpass filter."""
        nyq = 0.5 * fs
        low = max(lowcut / nyq, 1e-5)
        high = min(highcut / nyq, 0.99)
        return butter(order, [low, high], btype="band")

    def _apply_noise_cancellation(self, raw_audio_bytes: bytes) -> bytes:
        """
        Bandpass filter: removes low rumble (<80 Hz) and high hiss (>8 kHz).
        Isolates typical human speech frequencies.
        """
        audio_data = np.frombuffer(raw_audio_bytes, dtype=np.int16)
        if audio_data.size == 0:
            return raw_audio_bytes

        b, a = self._butter_bandpass(80, 8000, self.sample_rate, order=4)
        filtered = lfilter(b, a, audio_data.astype(np.float64))
        filtered = np.clip(filtered, -32768, 32767).astype(np.int16)
        return filtered.tobytes()

    def _prepare_clean_pcm(self, audio: sr.AudioData) -> bytes:
        """Resample to 16 kHz mono PCM, then apply DSP noise cancellation."""
        raw_data = audio.get_raw_data()
        sample_rate = audio.sample_rate
        sample_width = audio.sample_width
        channels = 1

        if sample_width != 2:
            raw_data = audioop.lin2lin(raw_data, sample_width, 2)

        if sample_rate != self.sample_rate:
            raw_data, _ = audioop.ratecv(
                raw_data, 2, channels, sample_rate, self.sample_rate, None
            )

        return self._apply_noise_cancellation(raw_data)

    def _write_pcm_wav(self, pcm_bytes: bytes, wav_path: str) -> None:
        with wave.open(wav_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(pcm_bytes)

    def _cleanup_temp(self) -> None:
        if os.path.exists(self.temp_wav):
            try:
                os.remove(self.temp_wav)
            except OSError:
                pass

    @staticmethod
    def _format_whisper_error(returncode: int, stderr: str, stdout: str) -> str:
        if returncode in (WIN_DLL_NOT_FOUND, -1073741515):
            return (
                "Whisper failed to start (missing DLL). Extract the full "
                "whisper-bin-x64.zip into whisper_bin/, including ggml*.dll."
            )
        message = (stderr or stdout or "").strip()
        if "deprecated" in message.lower() and "whisper-cli" in message.lower():
            return (
                "main.exe is deprecated. Use whisper-cli.exe from the "
                "whisper-bin-x64.zip release."
            )
        return message or f"Whisper exited with code {returncode}"

    @staticmethod
    def _parse_transcription(stdout: str) -> str:
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        return lines[-1] if lines else ""

    @staticmethod
    def _is_artifact(transcription: str) -> bool:
        normalized = transcription.lower().strip().strip(".")
        if not normalized:
            return True
        if normalized in WHISPER_ARTIFACTS:
            return True
        if any(normalized.startswith(prefix) for prefix in WHISPER_ARTIFACT_PREFIXES):
            return True
        # Whisper silence/noise tags like [BLANK_AUDIO]
        if normalized.startswith("[") and normalized.endswith("]"):
            return True
        return False

    def _capture_speech(self) -> sr.AudioData | None:
        """Open the mic, optionally calibrate once, and capture one utterance."""
        print("\n[Jarvis Core: Monitoring Mic Input...]")

        for attempt in range(2):
            source = sr.Microphone()
            try:
                source.__enter__()

                if not self._ambient_calibrated:
                    try:
                        self.recognizer.adjust_for_ambient_noise(
                            source, duration=0.6
                        )
                        self.recognizer.energy_threshold = max(
                            self.recognizer.energy_threshold, 300
                        )
                    except OSError as exc:
                        print(
                            f"[Mic calibration skipped: {exc}. "
                            "Using default threshold.]"
                        )
                    self._ambient_calibrated = True

                try:
                    return self.recognizer.listen(
                        source, timeout=4, phrase_time_limit=8
                    )
                except sr.WaitTimeoutError:
                    print("[No speech detected — timed out waiting.]")
                    return None
            except OSError as exc:
                if attempt == 0:
                    print(
                        f"[Microphone busy ({exc}). "
                        "Retrying in a moment...]"
                    )
                    time.sleep(0.4)
                    continue
                self.log.error(
                    "Microphone error after retry: %s", exc, exc_info=True
                )
                print(f"[Microphone error: {exc}. Skipping this cycle.]")
                return None
            finally:
                try:
                    source.__exit__(None, None, None)
                except OSError:
                    pass

        return None

    def listen_and_transcribe(self) -> str | None:
        audio = self._capture_speech()
        if audio is None:
            return None

        try:
            bin_path = self.resolve_bin_path()
            bin_dir = os.path.dirname(bin_path)
            model_abs = os.path.abspath(self.model_path)
            wav_abs = os.path.abspath(self.temp_wav)

            # Layer 2: resample + bandpass DSP filter, write valid WAV
            clean_pcm = self._prepare_clean_pcm(audio)
            self._write_pcm_wav(clean_pcm, wav_abs)

            command = [
                bin_path,
                "-m",
                model_abs,
                "-f",
                wav_abs,
                "-nt",
            ]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                shell=False,
                cwd=bin_dir,
            )

            if result.returncode != 0:
                err = self._format_whisper_error(
                    result.returncode,
                    result.stderr,
                    result.stdout,
                )
                self.log.error("Whisper error: %s", err)
                print(f"[Whisper error: {err}]")
                return None

            transcription = self._parse_transcription(result.stdout)
            if transcription and not self._is_artifact(transcription):
                print(f"You: {transcription}")
                return transcription

            if transcription:
                print("[Ignored whisper artifact transcription.]")
            else:
                print("[Whisper returned empty transcription.]")
            return None

        except FileNotFoundError as exc:
            self.log.error("Whisper setup error: %s", exc, exc_info=True)
            print(f"[Whisper setup error: {exc}]")
            return None
        except OSError as exc:
            self.log.error("Audio file error: %s", exc, exc_info=True)
            print(f"[Audio file error: {exc}]")
            return None
        finally:
            self._cleanup_temp()
