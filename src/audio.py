import audioop
import os
import subprocess
import wave

import speech_recognition as sr

WHISPER_CANDIDATES = (
    "whisper_bin/whisper-cli.exe",
    "whisper_bin/main.exe",
)

# Windows STATUS_DLL_NOT_FOUND
WIN_DLL_NOT_FOUND = 3221225781


class OfflineAudioInput:
    """Offline microphone input using whisper.cpp."""

    def __init__(
        self,
        model_path: str = "models/ggml-tiny.en.bin",
        bin_path: str = "whisper_bin/whisper-cli.exe",
        temp_wav: str = "temp_input.wav",
    ):
        self.model_path = model_path
        self.bin_path = bin_path
        self.temp_wav = temp_wav
        self.recognizer = sr.Recognizer()
        self._resolved_bin: str | None = None

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
        missing = [dll for dll in required_dlls if not os.path.isfile(os.path.join(bin_dir, dll))]
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

    def _write_whisper_wav(self, audio: sr.AudioData, wav_path: str) -> None:
        """Write 16 kHz mono PCM WAV without requiring ffmpeg."""
        raw_data = audio.get_raw_data()
        sample_rate = audio.sample_rate
        sample_width = audio.sample_width
        channels = 1

        if sample_width != 2:
            raw_data = audioop.lin2lin(raw_data, sample_width, 2)
            sample_width = 2

        if sample_rate != 16000:
            raw_data, _ = audioop.ratecv(
                raw_data, sample_width, channels, sample_rate, 16000, None
            )
            sample_rate = 16000

        with wave.open(wav_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(raw_data)

    def listen_and_transcribe(self) -> str | None:
        with sr.Microphone() as source:
            print("\n[Jarvis Core: Monitoring Mic Input...]")
            self.recognizer.adjust_for_ambient_noise(source, duration=0.4)
            try:
                audio = self.recognizer.listen(source, timeout=4, phrase_time_limit=8)
            except sr.WaitTimeoutError:
                print("[No speech detected — timed out waiting.]")
                return None

        try:
            bin_path = self.resolve_bin_path()
            bin_dir = os.path.dirname(bin_path)
            model_abs = os.path.abspath(self.model_path)
            wav_abs = os.path.abspath(self.temp_wav)

            self._write_whisper_wav(audio, wav_abs)

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
                print(f"[Whisper error: {err}]")
                return None

            transcription = self._parse_transcription(result.stdout)
            if transcription:
                print(f"You: {transcription}")
                return transcription

            print("[Whisper returned empty transcription.]")
            return None

        except FileNotFoundError as exc:
            print(f"[Whisper setup error: {exc}]")
            return None
        except OSError as exc:
            print(f"[Audio file error: {exc}]")
            return None
        finally:
            self._cleanup_temp()
