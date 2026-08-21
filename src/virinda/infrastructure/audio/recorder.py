from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


class AudioRecorderError(RuntimeError):
    """Raised when audio capture fails to start or execute."""


class LinuxAudioRecorder:
    """Non-blocking Linux audio recorder using pw-record or arecord in a killable process group."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self._proc: Optional[subprocess.Popen] = None
        self._output_path: Optional[Path] = None
        self._backend: Optional[str] = None
        self._detect_backend()

    def _detect_backend(self) -> None:
        if shutil.which("pw-record"):
            self._backend = "pw-record"
        elif shutil.which("arecord"):
            self._backend = "arecord"
        elif shutil.which("sox"):
            self._backend = "sox"
        else:
            self._backend = None

    @property
    def is_available(self) -> bool:
        return self._backend is not None

    @property
    def is_recording(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start_recording(self, output_path: Optional[Path] = None) -> Path:
        if self.is_recording:
            raise AudioRecorderError("Recorder is already active")

        if not self._backend:
            raise AudioRecorderError(
                "No audio capture utility found on host (pw-record, arecord, sox)."
            )

        if output_path:
            self._output_path = Path(output_path).expanduser().resolve()
        else:
            fd, tmp_file = tempfile.mkstemp(prefix="virinda_mic_", suffix=".wav")
            os.close(fd)
            self._output_path = Path(tmp_file)

        self._output_path.parent.mkdir(parents=True, exist_ok=True)

        if self._backend == "pw-record":
            cmd = [
                "pw-record",
                "--rate",
                str(self.sample_rate),
                "--channels",
                str(self.channels),
                "--format",
                "s16",
                str(self._output_path),
            ]
        elif self._backend == "arecord":
            cmd = [
                "arecord",
                "-f",
                "S16_LE",
                "-r",
                str(self.sample_rate),
                "-c",
                str(self.channels),
                "-t",
                "wav",
                "-q",
                str(self._output_path),
            ]
        else:  # sox
            cmd = [
                "rec",
                "-r",
                str(self.sample_rate),
                "-c",
                str(self.channels),
                "-b",
                "16",
                "-q",
                str(self._output_path),
            ]

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # Isolate in its own process group
            )
        except Exception as exc:
            self._proc = None
            raise AudioRecorderError(f"Failed to spawn {self._backend}: {exc}") from exc

        return self._output_path

    def stop_recording(self) -> Path:
        """Stops recording gracefully and ensures audio file is finalized."""
        if not self._proc or not self._output_path:
            raise AudioRecorderError("No active recording to stop")

        proc = self._proc
        self._proc = None

        if proc.poll() is None:
            try:
                # Send SIGINT first to let WAV header write cleanly
                os.killpg(os.getpgid(proc.pid), signal.SIGINT)
                proc.wait(timeout=1.5)
            except (subprocess.TimeoutExpired, ProcessLookupError, OSError):
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    proc.wait(timeout=0.5)
                except (ProcessLookupError, OSError):
                    pass

        return self._output_path

    def cancel_recording(self) -> None:
        """Cancels recording and discards temporary audio file."""
        if self._proc:
            proc = self._proc
            self._proc = None
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=0.5)
            except (ProcessLookupError, OSError):
                pass

        if self._output_path and self._output_path.exists():
            try:
                self._output_path.unlink()
            except OSError:
                pass
            self._output_path = None
