"""
Conversation transcript and streaming dialogue widget for the VirindaAI TUI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from rich.panel import Panel
from rich.table import Table
from rich.text import Text


@dataclass
class DialogueMessage:
    speaker: str  # "User" or "VirindaAI"
    text: str
    is_streaming: bool = False


class ConversationBuffer:
    """Manages a rolling conversation transcript for TUI display."""

    def __init__(self, max_messages: int = 50) -> None:
        self.messages: List[DialogueMessage] = []
        self.max_messages = max_messages

    def add_user_message(self, text: str) -> None:
        self.messages.append(DialogueMessage(speaker="User", text=text, is_streaming=False))
        self._trim()

    def start_assistant_message(self) -> None:
        self.messages.append(DialogueMessage(speaker="VirindaAI", text="", is_streaming=True))
        self._trim()

    def append_assistant_token(self, token: str) -> None:
        if not self.messages or self.messages[-1].speaker != "VirindaAI":
            self.start_assistant_message()
        self.messages[-1].text += token

    def finish_assistant_message(self) -> None:
        if self.messages and self.messages[-1].speaker == "VirindaAI":
            self.messages[-1].is_streaming = False

    def clear(self) -> None:
        self.messages.clear()

    def _trim(self) -> None:
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages :]


def render_conversation(buffer: ConversationBuffer, height: int = 14) -> Panel:
    """Renders the retained conversation dialogue window with clean minimalist borders."""
    if not buffer.messages:
        empty_text = Text(
            "\n  No speech dialogue registered.\n  Press [ENTER] to start recording or speak ambient wake phrase.",
            style="dim italic #64748B",
        )
        return Panel(
            empty_text,
            title="[bold #38BDF8]DIALOGUE TRANSCRIPT[/]",
            border_style="#334155",
            padding=(0, 1),
        )

    table = Table.grid(expand=True, padding=(0, 0, 1, 0))
    table.add_column("content")

    # Display the most recent messages that fit
    for msg in buffer.messages[-6:]:
        block = Text()
        if msg.speaker == "User":
            block.append("  ▸ USER ", style="bold #38BDF8")
            block.append("│ ", style="dim #475569")
            block.append(f"{msg.text.strip()}\n", style="#F1F5F9")
        else:
            block.append("  ▸ VIRINDA ", style="bold #818CF8")
            block.append("│ ", style="dim #475569")
            stream_tag = " ▌" if msg.is_streaming else ""
            block.append(f"{msg.text.strip()}{stream_tag}\n", style="#E2E8F0")
        table.add_row(block)

    return Panel(
        table,
        title="[bold #38BDF8]DIALOGUE TRANSCRIPT[/]",
        border_style="#334155",
        padding=(0, 1),
    )
