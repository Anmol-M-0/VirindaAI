"""
Header widget for the VirindaAI TUI.
"""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from virinda.interfaces.tui.events import TUIState

STATE_BADGES = {
    TUIState.IDLE: ("[bold white on #333333] IDLE ⚪ [/]", "Ready for voice input"),
    TUIState.LISTENING: ("[bold white on #d70000] LISTENING 🔴 [/]", "Recording microphone..."),
    TUIState.THINKING: ("[bold black on #ffaf00] THINKING 🧠 [/]", "Processing response..."),
    TUIState.SPEAKING: ("[bold white on #0087d7] SPEAKING 🔊 [/]", "Streaming voice audio..."),
    TUIState.ERROR: ("[bold white on #af0000] ERROR ⚠️ [/]", "System diagnostic issue"),
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

    left_text = Text.from_markup(f"[bold cyan]✦ VirindaAI Voice Desktop[/] [dim]({mode})[/]")
    center_text = Text.from_markup(f"{badge_markup} [dim italic]{status_text}[/]")
    right_text = Text.from_markup(
        f"[dim]Engine:[/] [bold green]{model}[/] [dim]•[/] [dim]Audio:[/] [bold blue]{backend}[/]"
    )

    table.add_row(left_text, center_text, right_text)
    return Panel(table, style="bold bright_blue", padding=(0, 1))
