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
        k1 = Text.from_markup("[bold #FFFFFF on #DC2626] [ENTER] Stop Recording [/]")
    else:
        k1 = Text.from_markup("[bold #FFFFFF on #2563EB] [ENTER] Push-To-Talk [/]")

    if state in (TUIState.SPEAKING, TUIState.THINKING):
        k2 = Text.from_markup("[bold #FFFFFF on #D97706] [ESC / B] Barge-In [/]")
    else:
        k2 = Text.from_markup("[dim #64748B] [ESC / B] Barge-In [/]")

    k3 = Text.from_markup("[dim #94A3B8] [C] Clear [/]")
    k4 = Text.from_markup("[bold #CBD5E1 on #1E293B] [Q] Quit [/]")

    table.add_row(k1, k2, k3, k4)
    return Panel(table, style="#334155", padding=(0, 1))
