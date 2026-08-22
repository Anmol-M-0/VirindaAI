from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

from virinda.application.service import AssistantService
from virinda.infrastructure.desktop.probes import DesktopContextSnapshot, detect_desktop_context
from virinda.infrastructure.desktop.screen import ScreenGroundingProbe, ScreenshotResult

logger = logging.getLogger(__name__)


class ScreenVisionQueryEngine:
    """Multimodal vision query engine grounded in active desktop state and screen capture."""

    def __init__(
        self,
        service: AssistantService,
        screen_probe: Optional[ScreenGroundingProbe] = None,
    ) -> None:
        self.service = service
        self.screen_probe = screen_probe or ScreenGroundingProbe()

    def query_screen(
        self,
        question: str,
        *,
        cleanup: bool = True,
    ) -> dict[str, Any]:
        """Captures active screen, builds grounded vision context, and queries the assistant."""
        start_time = time.time()
        desktop_ctx: DesktopContextSnapshot = detect_desktop_context()
        screenshot_path: Optional[Path] = None
        backend = "none"

        try:
            if self.screen_probe.is_available:
                try:
                    res: ScreenshotResult = self.screen_probe.capture()
                    screenshot_path = res.image_path
                    backend = res.backend
                except Exception as exc:
                    logger.warning(
                        "Screen capture failed, proceeding with desktop context only: %s", exc
                    )

            # Build grounded multimodal query prompt
            context_lines = [
                "### Active Desktop Context",
                f"- Focused Application: {desktop_ctx.active_app}",
                f"- Window Title: {desktop_ctx.window_title}",
                f"- Compositor: {desktop_ctx.compositor}",
                f"- Capture Backend: {backend}",
            ]
            if screenshot_path and screenshot_path.exists():
                context_lines.append(f"- Screenshot File: {screenshot_path.name}")

            prompt = (
                f"{chr(10).join(context_lines)}\n\n"
                f"### User Screen Question:\n{question}\n\n"
                "Please analyze what is on the screen and provide a clear, concise answer."
            )

            # Query AssistantService
            answer = self.service.ask(prompt)

            latency_ms = (time.time() - start_time) * 1000.0
            return {
                "ok": True,
                "question": question,
                "answer": answer,
                "desktop_context": desktop_ctx.to_dict(),
                "screenshot_captured": screenshot_path is not None and screenshot_path.exists(),
                "latency_ms": round(latency_ms, 2),
            }

        finally:
            if cleanup and screenshot_path and screenshot_path.exists():
                try:
                    screenshot_path.unlink()
                except OSError:
                    pass
