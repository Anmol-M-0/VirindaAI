"""
Footer hotkey legend widget for the VirindaAI TUI.
"""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from virinda.interfaces.tui.events import TUIState


def render_footer(state: TUIState = TUIState.IDLE) -> Panel:
    """Renders the contextual keyboard shortcut controls footer."""
    table = Table.grid(expand=True)
    table.add_column("c1", justify="left")
    table.add_column("c2", justify="center")
    table.add_column("c3", justify="center")
    table.add_column("c4", justify="right")

    if state == TUIState.LISTENING:
        k1 = Text.from_markup("[bold black on red] [ENTER] Finish Speaking [/]")
    else:
        k1 = Text.from_markup("[bold black on green] [ENTER] Talk [/]")

    if state in (TUIState.SPEAKING, TUIState.THINKING):
        k2 = Text.from_markup("[bold black on yellow] [B] Barge-In / Stop [/]")
    else:
        k2 = Text.from_markup("[dim] [B] Barge-In [/]")

    k3 = Text.from_markup("[dim] [C] Clear History [/]")
    k4 = Text.from_markup("[bold black on bright_white] [Q] Quit [/]")

    table.add_row(k1, k2, k3, k4)
    return Panel(table, style="dim bright_blue", padding=(0, 1))
