from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(slots=True)
class ScreenshotResult:
    image_path: Path
    backend: str
    timestamp: float = 0.0


class ScreenGroundingProbe:
    """Non-blocking screen capture utility for multimodal visual grounding on Linux."""

    def __init__(self) -> None:
        self._backend: Optional[str] = None
        self._detect_backend()

    def _detect_backend(self) -> None:
        if shutil.which("grim"):
            self._backend = "grim"
        elif shutil.which("scrot"):
            self._backend = "scrot"
        elif shutil.which("import"):
            self._backend = "import"
        else:
            self._backend = None

    @property
    def is_available(self) -> bool:
        return self._backend is not None

    def capture(self, output_path: Optional[Path] = None) -> ScreenshotResult:
        if not self._backend:
            raise RuntimeError("No screenshot utility found on host (grim, scrot, import).")

        if output_path:
            out_file = Path(output_path).expanduser().resolve()
        else:
            fd, tmp = tempfile.mkstemp(prefix="virinda_screen_", suffix=".png")
            os.close(fd)
            out_file = Path(tmp)

        out_file.parent.mkdir(parents=True, exist_ok=True)

        cmd: list[str] = []
        if self._backend == "grim":
            cmd = ["grim", str(out_file)]
        elif self._backend == "scrot":
            cmd = ["scrot", "--overwrite", str(out_file)]
        else:  # import
            cmd = ["import", "-window", "root", str(out_file)]

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                timeout=2.0,
            )
            if res.returncode != 0:
                raise RuntimeError(
                    f"Screenshot utility {self._backend} exited with code {res.returncode}"
                )
        except Exception as exc:
            if out_file.exists():
                try:
                    out_file.unlink()
                except OSError:
                    pass
            raise RuntimeError(f"Failed to capture screenshot with {self._backend}: {exc}") from exc

        return ScreenshotResult(
            image_path=out_file,
            backend=self._backend,
            timestamp=time.time(),
        )
