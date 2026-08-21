from __future__ import annotations

import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Optional


class AudioPlayerError(RuntimeError):
    """Raised when audio playback fails."""


class LinuxAudioPlayer:
    """Non-blocking Linux audio player with immediate barge-in stop support."""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._backend: Optional[str] = None
        self._detect_backend()

    def _detect_backend(self) -> None:
        if shutil.which("pw-play"):
            self._backend = "pw-play"
        elif shutil.which("aplay"):
            self._backend = "aplay"
        elif shutil.which("paplay"):
            self._backend = "paplay"
        else:
            self._backend = None

    @property
    def is_available(self) -> bool:
        return self._backend is not None

    @property
    def is_playing(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def play_wav(self, wav_path: Path, block: bool = False) -> None:
        """Play a WAV audio file non-blockingly (or blockingly if requested)."""
        self.stop()

        if not self._backend:
            raise AudioPlayerError(
                "No audio player utility found on host (pw-play, aplay, paplay)."
            )

        p = Path(wav_path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Audio file does not exist: {p}")

        cmd = [self._backend, str(p)]
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # Isolate in its own process group
            )
            if block:
                self._proc.wait()
        except Exception as exc:
            self._proc = None
            raise AudioPlayerError(f"Failed to play audio with {self._backend}: {exc}") from exc

    def stop(self) -> None:
        """Immediately stop any active playback (hard barge-in)."""
        if self._proc:
            proc = self._proc
            self._proc = None
            if proc.poll() is None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    proc.wait(timeout=0.5)
                except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
                    pass
