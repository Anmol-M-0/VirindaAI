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
    clamped_db = max(-60.0, min(0.0, rms_dbfs))
    ratio = (clamped_db + 60.0) / 60.0
    fill_count = int(round(ratio * width))

    green_cap = int(width * 0.70)  # -18 dBFS threshold
    yellow_cap = int(width * 0.90)  # -6 dBFS threshold

    t = Text()
    for i in range(width):
        if i < fill_count:
            if i < green_cap:
                t.append("█", style="#10B981")
            elif i < yellow_cap:
                t.append("█", style="#F59E0B")
            else:
                t.append("█", style="#EF4444")
        else:
            t.append("░", style="#1E293B")

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

    label_style = "bold #38BDF8" if is_active else "dim #64748B"
    label = Text("SIGNAL", style=label_style)

    vu_bar = format_vu_bar(rms_dbfs if is_active else -60.0, width=bar_width)

    if is_active:
        val_text = Text(f"{rms_dbfs:+5.1f} dBFS", style="bold #F1F5F9")
    else:
        val_text = Text("  SILENT", style="dim #475569")

    table.add_row(label, vu_bar, val_text)
    return Panel(table, style="#334155", padding=(0, 1))
