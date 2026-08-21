from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional


class SpeechError(RuntimeError):
    """Raised when STT or TTS processing fails."""


class NativeTTS:
    """Native Linux Speech Synthesizer using spd-say, espeak-ng, or piper with instant stop."""

    def __init__(self, voice: Optional[str] = None, rate: int = 0) -> None:
        self.voice = voice
        self.rate = rate
        self._proc: Optional[subprocess.Popen] = None
        self._backend: Optional[str] = None
        self._detect_backend()

    def _detect_backend(self) -> None:
        if shutil.which("spd-say"):
            self._backend = "spd-say"
        elif shutil.which("espeak-ng"):
            self._backend = "espeak-ng"
        elif shutil.which("espeak"):
            self._backend = "espeak"
        else:
            self._backend = None

    @property
    def is_available(self) -> bool:
        return self._backend is not None

    @property
    def is_speaking(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def speak(self, text: str, block: bool = True) -> None:
        """Speak the given text aloud. Stops any ongoing utterance first."""
        self.stop()
        clean_text = text.strip()
        if not clean_text:
            return

        if not self._backend:
            # Fallback to no-op if no TTS binary is installed
            return

        if self._backend == "spd-say":
            cmd = ["spd-say", "-e"]
            if block:
                cmd.append("-w")  # wait till spoken
            if self.rate != 0:
                cmd.extend(["-r", str(self.rate)])
            cmd.append(clean_text)
        elif self._backend in ("espeak-ng", "espeak"):
            cmd = [self._backend, clean_text]
        else:
            return

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            if block:
                self._proc.wait()
        except Exception as exc:
            self._proc = None
            raise SpeechError(f"Failed to speak text via {self._backend}: {exc}") from exc

    def stop(self) -> None:
        """Instantly stop speech (barge-in)."""
        if self._proc:
            proc = self._proc
            self._proc = None
            if proc.poll() is None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    proc.wait(timeout=0.5)
                except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
                    pass
        if self._backend == "spd-say" and shutil.which("spd-say"):
            try:
                subprocess.run(
                    ["spd-say", "--cancel"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=0.5,
                )
            except Exception:
                pass


class GroqWhisperSTT:
    """Fast Cloud STT using Groq Whisper API (whisper-large-v3-turbo) with offline mock fallback."""

    def __init__(
        self, api_key: Optional[str] = None, model: str = "whisper-large-v3-turbo"
    ) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model

    def transcribe_file(self, wav_path: Path) -> str:
        p = Path(wav_path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Audio file not found: {p}")

        if not self.api_key:
            # Fallback if no GROQ_API_KEY configured
            return ""

        audio_bytes = p.read_bytes()
        if len(audio_bytes) < 1000:
            # Empty or too short
            return ""

        boundary = "----VirindaVoiceBoundary7MA4YWxkTrZu0gW"
        body = bytearray()

        # model field
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="model"\r\n\r\n')
        body.extend(f"{self.model}\r\n".encode("utf-8"))

        # response_format field
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="response_format"\r\n\r\n')
        body.extend(b"json\r\n")

        # file field
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="file"; filename="{p.name}"\r\n'.encode("utf-8")
        )
        body.extend(b"Content-Type: audio/wav\r\n\r\n")
        body.extend(audio_bytes)
        body.extend(b"\r\n")

        # end boundary
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))

        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            data=bytes(body),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("text", "").strip()
        except Exception as exc:
            raise SpeechError(f"Groq Whisper transcription failed: {exc}") from exc
