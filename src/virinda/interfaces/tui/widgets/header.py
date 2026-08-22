"""
Header widget for the VirindaAI TUI.
"""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from virinda.interfaces.tui.events import TUIState

STATE_BADGES = {
    TUIState.IDLE: ("[bold #94A3B8 on #1E293B]  ● STANDBY  [/]", "Awaiting voice trigger"),
    TUIState.LISTENING: ("[bold #FFFFFF on #DC2626]  ● LISTENING  [/]", "Capturing microphone..."),
    TUIState.THINKING: ("[bold #FFFFFF on #4F46E5]  ● PROCESSING  [/]", "Inferencing response..."),
    TUIState.SPEAKING: ("[bold #FFFFFF on #059669]  ● OUTPUT  [/]", "Streaming audio playback..."),
    TUIState.ERROR: ("[bold #FFFFFF on #B91C1C]  ● FAULT  [/]", "Diagnostic issue detected"),
}


def render_header(
    state: TUIState = TUIState.IDLE,
    model: str = "whisper.cpp / local",
    backend: str = "PipeWire",
    mode: str = "Push-To-Talk",
) -> Panel:
    """Renders the top branding and cognitive state status bar."""
    table = Table.grid(expand=True)
    table.add_column("left", justify="left", ratio=3)
    table.add_column("center", justify="center", ratio=4)
    table.add_column("right", justify="right", ratio=3)

    badge_markup, status_text = STATE_BADGES.get(state, STATE_BADGES[TUIState.IDLE])

    left_text = Text.from_markup(
        f"[bold #38BDF8]VIRINDA[/] [dim #64748B]//[/] [bold #F8FAFC]AMBIENT RUNTIME[/] [dim #64748B]({mode})[/]"
    )
    center_text = Text.from_markup(f"{badge_markup} [dim italic #94A3B8]{status_text}[/]")
    right_text = Text.from_markup(
        f"[dim #64748B]MODEL:[/] [bold #34D399]{model}[/] [dim #64748B]│[/] [dim #64748B]AUDIO:[/] [bold #60A5FA]{backend}[/]"
    )

    table.add_row(left_text, center_text, right_text)
    return Panel(table, style="#334155", padding=(0, 1))
