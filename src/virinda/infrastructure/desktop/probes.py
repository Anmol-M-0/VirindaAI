from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class DesktopContextSnapshot:
    active_app: str
    window_title: str
    compositor: str
    pid: Optional[int] = None
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "active_app": self.active_app,
            "window_title": self.window_title,
            "compositor": self.compositor,
            "pid": self.pid,
            "timestamp": self.timestamp,
        }


class DesktopProbe:
    """Base protocol for compositor-specific window context probes."""

    def probe(self) -> Optional[DesktopContextSnapshot]:
        raise NotImplementedError


class HyprlandProbe(DesktopProbe):
    def probe(self) -> Optional[DesktopContextSnapshot]:
        if not shutil.which("hyprctl"):
            return None
        try:
            res = subprocess.run(
                ["hyprctl", "activewindow", "-j"],
                capture_output=True,
                text=True,
                timeout=0.4,
            )
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                app = data.get("class") or data.get("initialClass") or "unknown"
                title = data.get("title", "")
                pid = data.get("pid")
                return DesktopContextSnapshot(
                    active_app=app,
                    window_title=title,
                    compositor="hyprland",
                    pid=pid if isinstance(pid, int) else None,
                    timestamp=time.time(),
                )
        except Exception:
            pass
        return None


class SwayProbe(DesktopProbe):
    def probe(self) -> Optional[DesktopContextSnapshot]:
        if not shutil.which("swaymsg"):
            return None
        try:
            res = subprocess.run(
                ["swaymsg", "-t", "get_tree"],
                capture_output=True,
                text=True,
                timeout=0.4,
            )
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)

                def find_focused(node: dict) -> Optional[dict]:
                    if node.get("focused"):
                        return node
                    for child in node.get("nodes", []) + node.get("floating_nodes", []):
                        found = find_focused(child)
                        if found:
                            return found
                    return None

                focused = find_focused(data)
                if focused:
                    app = (
                        focused.get("app_id")
                        or focused.get("window_properties", {}).get("class")
                        or "unknown"
                    )
                    title = focused.get("name", "")
                    pid = focused.get("pid")
                    return DesktopContextSnapshot(
                        active_app=app,
                        window_title=title,
                        compositor="sway",
                        pid=pid,
                        timestamp=time.time(),
                    )
        except Exception:
            pass
        return None


class X11Probe(DesktopProbe):
    def probe(self) -> Optional[DesktopContextSnapshot]:
        if not shutil.which("xdotool"):
            return None
        try:
            wid_res = subprocess.run(
                ["xdotool", "getactivewindow"],
                capture_output=True,
                text=True,
                timeout=0.3,
            )
            if wid_res.returncode != 0 or not wid_res.stdout.strip():
                return None
            wid = wid_res.stdout.strip()

            title_res = subprocess.run(
                ["xdotool", "getwindowname", wid],
                capture_output=True,
                text=True,
                timeout=0.3,
            )
            title = title_res.stdout.strip() if title_res.returncode == 0 else ""

            pid_res = subprocess.run(
                ["xdotool", "getwindowpid", wid],
                capture_output=True,
                text=True,
                timeout=0.3,
            )
            pid = (
                int(pid_res.stdout.strip())
                if pid_res.returncode == 0 and pid_res.stdout.strip().isdigit()
                else None
            )

            # Get class name
            app = "x11-app"
            if shutil.which("xprop"):
                xprop_res = subprocess.run(
                    ["xprop", "-id", wid, "WM_CLASS"],
                    capture_output=True,
                    text=True,
                    timeout=0.3,
                )
                if xprop_res.returncode == 0 and "=" in xprop_res.stdout:
                    parts = xprop_res.stdout.split("=")[1].strip().replace('"', "").split(",")
                    if parts:
                        app = parts[-1].strip()

            return DesktopContextSnapshot(
                active_app=app,
                window_title=title,
                compositor="x11",
                pid=pid,
                timestamp=time.time(),
            )
        except Exception:
            pass
        return None


class DesktopProbeRegistry:
    """Detects active desktop window and application across Linux compositors."""

    def __init__(self) -> None:
        self.probes: list[DesktopProbe] = [
            HyprlandProbe(),
            SwayProbe(),
            X11Probe(),
        ]

    def detect(self) -> DesktopContextSnapshot:
        for probe in self.probes:
            snapshot = probe.probe()
            if snapshot:
                return snapshot

        # Fallback if no window or headless
        session_type = os.getenv("XDG_SESSION_TYPE", "unknown")
        return DesktopContextSnapshot(
            active_app="desktop",
            window_title="",
            compositor=session_type,
            pid=None,
            timestamp=time.time(),
        )


_DEFAULT_REGISTRY = DesktopProbeRegistry()


def detect_desktop_context() -> DesktopContextSnapshot:
    """Top-level utility function to get current focused desktop window context."""
    return _DEFAULT_REGISTRY.detect()
