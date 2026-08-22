from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


class SpeechError(RuntimeError):
    """Raised when STT or TTS processing fails."""


# ==============================================================================
# Local-First TTS (Text-To-Speech)
# ==============================================================================


class NativeTTS:
    """Native Linux Speech Synthesizer using piper, spd-say, espeak-ng, or mimic3 with instant stop."""

    def __init__(self, voice: Optional[str] = None, rate: int = 0) -> None:
        self.voice = voice
        self.rate = rate
        self._proc: Optional[subprocess.Popen] = None
        self._backend: Optional[str] = None
        self._detect_backend()

    def _detect_backend(self) -> None:
        if shutil.which("piper"):
            self._backend = "piper"
        elif shutil.which("spd-say"):
            self._backend = "spd-say"
        elif shutil.which("espeak-ng"):
            self._backend = "espeak-ng"
        elif shutil.which("espeak"):
            self._backend = "espeak"
        elif shutil.which("mimic3"):
            self._backend = "mimic3"
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
        if not clean_text or not self._backend:
            return

        cmd: list[str] = []
        if self._backend == "spd-say":
            cmd = ["spd-say", "-e"]
            if block:
                cmd.append("-w")
            if self.rate != 0:
                cmd.extend(["-r", str(self.rate)])
            cmd.append(clean_text)
        elif self._backend in ("espeak-ng", "espeak"):
            cmd = [self._backend, clean_text]
        elif self._backend == "mimic3":
            cmd = ["mimic3", clean_text]
        elif self._backend == "piper":
            cmd = ["piper", "--output-raw"]
        else:
            return

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE if self._backend == "piper" else None,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            if self._backend == "piper" and self._proc.stdin:
                self._proc.stdin.write(clean_text.encode("utf-8"))
                self._proc.stdin.close()
            if block:
                try:
                    self._proc.wait(timeout=8.0)
                except subprocess.TimeoutExpired:
                    self.stop()
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
                    proc.wait(timeout=0.3)
                except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
                    pass
        if self._backend == "spd-say" and shutil.which("spd-say"):
            try:
                subprocess.run(
                    ["spd-say", "--cancel"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=0.3,
                )
            except Exception:
                pass


# ==============================================================================
# Local-First STT (Speech-To-Text) Engines
# ==============================================================================


class STTProvider(Protocol):
    """Protocol for local/cloud speech-to-text engines."""

    def transcribe_file(self, wav_path: Path) -> str: ...

    @property
    def is_available(self) -> bool: ...


class LocalWhisperSTT:
    """Offline local STT using whisper.cpp (whisper-cli / main) on Linux."""

    def __init__(self, model_path: Optional[Path] = None) -> None:
        self.model_path = model_path or self._find_model()
        self.binary_path = self._find_binary()

    def _find_binary(self) -> Optional[str]:
        for bin_name in ("whisper-cli", "whisper-cpp", "whisper", "main"):
            p = shutil.which(bin_name)
            if p:
                return p
        # Check standard local compilation paths
        for candidate in (
            Path.home() / ".local" / "bin" / "whisper-cli",
            Path.home() / "whisper.cpp" / "build" / "bin" / "whisper-cli",
            Path.home() / "whisper.cpp" / "main",
        ):
            if candidate.exists() and os.access(candidate, os.X_OK):
                return str(candidate)
        return None

    def _find_model(self) -> Optional[Path]:
        search_dirs = [
            Path.home() / ".local" / "share" / "virinda" / "models" / "whisper",
            Path.home() / ".local" / "share" / "whisper.cpp" / "models",
            Path("/usr/share/whisper.cpp/models"),
            Path.home() / "whisper.cpp" / "models",
        ]
        for d in search_dirs:
            if d.exists():
                for m in (
                    "ggml-base.en.bin",
                    "ggml-tiny.en.bin",
                    "ggml-small.en.bin",
                    "ggml-base.bin",
                ):
                    p = d / m
                    if p.exists():
                        return p
        return None

    @property
    def is_available(self) -> bool:
        return bool(self.binary_path and self.model_path and self.model_path.exists())

    def transcribe_file(self, wav_path: Path) -> str:
        if not self.is_available or not self.binary_path or not self.model_path:
            raise SpeechError("Local whisper.cpp binary or model not found on system.")

        p = Path(wav_path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Audio file not found: {p}")

        cmd = [
            self.binary_path,
            "-m",
            str(self.model_path),
            "-f",
            str(p),
            "--no-timestamps",
            "-l",
            "en",
        ]

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15.0,
                check=True,
            )
            return res.stdout.strip()
        except subprocess.TimeoutExpired as exc:
            raise SpeechError("Local Whisper STT timed out during transcription.") from exc
        except subprocess.CalledProcessError as exc:
            raise SpeechError(f"Local Whisper STT failed: {exc.stderr.strip()}") from exc


class LocalVoskSTT:
    """Offline local STT using Vosk Kaldi speech models."""

    def __init__(self, model_path: Optional[Path] = None) -> None:
        self.model_path = model_path or self._find_model()
        self._model: Optional[object] = None

    def _find_model(self) -> Optional[Path]:
        search_dirs = [
            Path.cwd() / "models" / "vosk",
            Path(__file__).parents[3] / "models" / "vosk",
            Path.home() / ".local" / "share" / "virinda" / "models" / "vosk",
            Path.home() / ".cache" / "vosk",
            Path("/usr/share/vosk"),
        ]
        for d in search_dirs:
            if d.exists():
                for sub in d.iterdir():
                    if sub.is_dir() and (sub / "am").exists():
                        return sub
        return None

    @property
    def is_available(self) -> bool:
        try:
            import vosk  # noqa: F401

            return self.model_path is not None and self.model_path.exists()
        except ImportError:
            return False

    def transcribe_file(self, wav_path: Path) -> str:
        if not self.is_available:
            raise SpeechError("Vosk Python package or offline model not installed.")

        p = Path(wav_path).expanduser().resolve()
        if not p.exists() or p.stat().st_size < 100:
            return ""

        import vosk

        if not self._model:
            self._model = vosk.Model(str(self.model_path))

        try:
            with wave.open(str(p), "rb") as wf:
                framerate = wf.getframerate()
                rec = vosk.KaldiRecognizer(self._model, framerate)
                rec.SetWords(True)

                results = []
                while True:
                    data = wf.readframes(4000)
                    if len(data) == 0:
                        break
                    if rec.AcceptWaveform(data):
                        res = json.loads(rec.Result())
                        if "text" in res and res["text"]:
                            results.append(res["text"])

                final_res = json.loads(rec.FinalResult())
                if "text" in final_res and final_res["text"]:
                    results.append(final_res["text"])

                return " ".join(results).strip()
        except Exception as exc:
            logger.warning("Vosk audio decoding error on %s: %s", p, exc)
            return ""


class GroqWhisperSTT:
    """Optional Cloud STT using Groq Whisper API (requires explicit opt-in and valid GROQ_API_KEY)."""

    def __init__(
        self, api_key: Optional[str] = None, model: str = "whisper-large-v3-turbo"
    ) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model

    @property
    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 10)

    def transcribe_file(self, wav_path: Path) -> str:
        p = Path(wav_path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Audio file not found: {p}")

        if not self.api_key:
            raise SpeechError("Groq API key not configured.")

        audio_bytes = p.read_bytes()
        if len(audio_bytes) < 1000:
            return ""

        boundary = "----VirindaVoiceBoundary7MA4YWxkTrZu0gW"
        body = bytearray()
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="model"\r\n\r\n')
        body.extend(f"{self.model}\r\n".encode("utf-8"))
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(b'Content-Disposition: form-data; name="response_format"\r\n\r\n')
        body.extend(b"json\r\n")
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="file"; filename="{p.name}"\r\n'.encode("utf-8")
        )
        body.extend(b"Content-Type: audio/wav\r\n\r\n")
        body.extend(audio_bytes)
        body.extend(b"\r\n")
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
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise SpeechError(
                    "Groq Whisper API key is unauthorized or forbidden. Check your GROQ_API_KEY or use local STT."
                ) from exc
            raise SpeechError(f"Groq Whisper HTTP error {exc.code}: {exc.reason}") from exc
        except Exception as exc:
            raise SpeechError(f"Groq Whisper transcription failed: {exc}") from exc


class MockSTT:
    """Offline mock speech-to-text transcriber for testing and demo environments."""

    def __init__(self, default_text: str = "Hello Virinda, what can you do?") -> None:
        self.default_text = default_text

    @property
    def is_available(self) -> bool:
        return True

    def transcribe_file(self, wav_path: Path) -> str:
        return self.default_text


# ==============================================================================
# SpeechToText: The Unified Local-First Facade
# ==============================================================================


class SpeechToText:
    """Authoritative Local-First Speech-To-Text Facade.

    Prioritizes local offline engines (whisper.cpp, Vosk) with zero network calls.
    Cloud Groq is strictly opt-in and never enabled by default.
    """

    def __init__(
        self,
        local_whisper: Optional[LocalWhisperSTT] = None,
        local_vosk: Optional[LocalVoskSTT] = None,
        groq_stt: Optional[GroqWhisperSTT] = None,
        cloud_fallback: bool = False,
        mock_mode: bool = False,
    ) -> None:
        self.local_whisper = local_whisper or LocalWhisperSTT()
        self.local_vosk = local_vosk or LocalVoskSTT()
        self.groq_stt = groq_stt or GroqWhisperSTT()
        self.cloud_fallback = cloud_fallback or bool(os.getenv("VIRINDA_STT_CLOUD_FALLBACK") == "1")
        self.mock_mode = mock_mode

    @property
    def active_engine_name(self) -> str:
        if self.mock_mode:
            return "mock"
        if self.local_whisper.is_available:
            return "whisper.cpp (local)"
        if self.local_vosk.is_available:
            return "vosk (local)"
        if self.cloud_fallback and self.groq_stt.is_available:
            return "groq-cloud (opt-in)"
        return "none (unconfigured)"

    def transcribe_file(self, wav_path: Path) -> str:
        """Transcribes audio file using the highest-priority local engine available."""
        if self.mock_mode:
            return MockSTT().transcribe_file(wav_path)

        # 1. Local whisper.cpp
        if self.local_whisper.is_available:
            try:
                return self.local_whisper.transcribe_file(wav_path)
            except Exception as exc:
                logger.warning("Local whisper.cpp failed: %s; falling back", exc)

        # 2. Local Vosk
        if self.local_vosk.is_available:
            try:
                return self.local_vosk.transcribe_file(wav_path)
            except Exception as exc:
                logger.warning("Local Vosk failed: %s; falling back", exc)

        # 3. Explicit opt-in cloud fallback
        if self.cloud_fallback and self.groq_stt.is_available:
            try:
                return self.groq_stt.transcribe_file(wav_path)
            except Exception as exc:
                logger.warning("Cloud STT fallback failed: %s", exc)

        # 4. If no local engine was available, fail cleanly with an informative message
        logger.warning("No local STT engine or model found on system (whisper.cpp, vosk).")
        raise SpeechError(
            "No local speech recognition engine or model found. "
            "Please ensure vosk-model is present in ~/.local/share/virinda/models/vosk/ or whisper.cpp is installed."
        )
