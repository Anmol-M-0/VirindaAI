"""
Real-time RMS dBFS audio VU meter widget for the VirindaAI TUI.
"""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def format_vu_bar(rms_dbfs: float, width: int = 36) -> Text:
    """
    Renders a colored VU meter bar across -60 dBFS to 0 dBFS.
    Green: [-60, -18 dBFS], Yellow: [-18, -6 dBFS], Red: [-6, 0 dBFS].
    """
    # Clamp dBFS between -60 and 0
    clamped_db = max(-60.0, min(0.0, rms_dbfs))
    # Normalized proportion from 0.0 to 1.0
    ratio = (clamped_db + 60.0) / 60.0
    fill_count = int(round(ratio * width))

    green_cap = int(width * 0.70)  # -18 dBFS threshold
    yellow_cap = int(width * 0.90)  # -6 dBFS threshold

    t = Text()
    for i in range(width):
        if i < fill_count:
            if i < green_cap:
                t.append("█", style="bold green")
            elif i < yellow_cap:
                t.append("█", style="bold yellow")
            else:
                t.append("█", style="bold red")
        else:
            t.append("░", style="dim white")

    return t


def render_vu_meter(
    rms_dbfs: float = -60.0,
    peak_dbfs: float = -60.0,
    is_active: bool = False,
    bar_width: int = 34,
) -> Panel:
    """Renders the audio energy panel with VU bar and dBFS readout."""
    table = Table.grid(expand=True)
    table.add_column("label", justify="left", ratio=2)
    table.add_column("bar", justify="center", ratio=6)
    table.add_column("val", justify="right", ratio=2)

    label_style = "bold yellow" if is_active else "dim"
    label = Text("MIC LEVEL", style=label_style)

    vu_bar = format_vu_bar(rms_dbfs if is_active else -60.0, width=bar_width)

    if is_active:
        val_text = Text(f"{rms_dbfs:+5.1f} dBFS", style="bold cyan")
    else:
        val_text = Text("  SILENCE", style="dim")

    table.add_row(label, vu_bar, val_text)
    border_style = "yellow" if is_active else "dim blue"
    return Panel(table, title="Audio Signal", border_style=border_style, padding=(0, 1))
