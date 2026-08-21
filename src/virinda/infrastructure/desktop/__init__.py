from virinda.infrastructure.desktop.probes import (
    DesktopContextSnapshot,
    DesktopProbeRegistry,
    detect_desktop_context,
)
from virinda.infrastructure.desktop.screen import ScreenGroundingProbe, ScreenshotResult

__all__ = [
    "DesktopContextSnapshot",
    "DesktopProbeRegistry",
    "detect_desktop_context",
    "ScreenGroundingProbe",
    "ScreenshotResult",
]
