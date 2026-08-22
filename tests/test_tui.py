"""
Unit tests for the VirindaAI Modular Terminal User Interface (TUI) package.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

from virinda.interfaces.tui.app import VirindaTUIApp
from virinda.interfaces.tui.bridge import TUIEventBridge
from virinda.interfaces.tui.events import (
    AssistantDelta,
    AudioLevelChanged,
    ErrorRaised,
    TranscriptDelta,
    TUIState,
    UICommandKind,
    VoiceStateChanged,
)
from virinda.interfaces.tui.widgets import (
    ConversationBuffer,
    format_vu_bar,
    render_conversation,
    render_footer,
    render_header,
    render_vu_meter,
)


def test_tui_event_bridge_lifecycle():
    bridge = TUIEventBridge(max_queue_size=32)

    # 1. State emission
    bridge.emit_state(TUIState.LISTENING, model="whisper-tiny", backend="PipeWire")
    event = bridge.events_queue.get_nowait()
    assert isinstance(event, VoiceStateChanged)
    assert event.state == TUIState.LISTENING
    assert event.model == "whisper-tiny"

    # 2. Transcript emission
    bridge.emit_transcript("Turn on desktop lights", is_final=True)
    event = bridge.events_queue.get_nowait()
    assert isinstance(event, TranscriptDelta)
    assert event.text == "Turn on desktop lights"
    assert event.is_final is True

    # 3. Assistant stream token
    bridge.emit_assistant_delta("Sure, ", is_final=False)
    event = bridge.events_queue.get_nowait()
    assert isinstance(event, AssistantDelta)
    assert event.text == "Sure, "
    assert event.is_final is False

    # 4. Error emission
    bridge.emit_error("Audio Device Error", "Microphone stream failed")
    event = bridge.events_queue.get_nowait()
    assert isinstance(event, ErrorRaised)
    assert event.title == "Audio Device Error"

    # 5. UI Command roundtrip
    bridge.post_command(UICommandKind.START_LISTENING)
    cmd = bridge.get_command(timeout=0.1)
    assert cmd is not None
    assert cmd.kind == UICommandKind.START_LISTENING


def test_tui_audio_level_throttling():
    bridge = TUIEventBridge(max_queue_size=100)

    # Rapid burst of 20 audio levels in < 1ms
    for i in range(20):
        bridge.emit_audio_level(rms_dbfs=-30.0 + i)

    # Throttling should only put 1 event in the queue
    assert bridge.events_queue.qsize() == 1
    ev = bridge.events_queue.get_nowait()
    assert isinstance(ev, AudioLevelChanged)


def test_conversation_buffer_and_streaming():
    buffer = ConversationBuffer(max_messages=5)

    buffer.add_user_message("Hello Virinda")
    assert len(buffer.messages) == 1
    assert buffer.messages[0].speaker == "User"
    assert buffer.messages[0].text == "Hello Virinda"

    buffer.start_assistant_message()
    buffer.append_assistant_token("Hi! ")
    buffer.append_assistant_token("How can I help?")
    buffer.finish_assistant_message()

    assert len(buffer.messages) == 2
    assert buffer.messages[1].speaker == "VirindaAI"
    assert buffer.messages[1].text == "Hi! How can I help?"
    assert buffer.messages[1].is_streaming is False

    # Test buffer capacity trimming
    for i in range(10):
        buffer.add_user_message(f"Msg {i}")

    assert len(buffer.messages) == 5
    assert buffer.messages[-1].text == "Msg 9"

    buffer.clear()
    assert len(buffer.messages) == 0


def test_widgets_rendering():
    console = Console(record=True, width=80)

    # 1. Header widget
    for state in (
        TUIState.IDLE,
        TUIState.LISTENING,
        TUIState.THINKING,
        TUIState.SPEAKING,
        TUIState.ERROR,
    ):
        panel = render_header(state=state, model="test-model", backend="ALSA")
        assert isinstance(panel, Panel)
        console.print(panel)

    # 2. VU meter formatting across dBFS bands
    bar_low = format_vu_bar(-55.0, width=30)
    bar_mid = format_vu_bar(-12.0, width=30)
    bar_high = format_vu_bar(-2.0, width=30)
    assert len(bar_low.plain) == 30
    assert len(bar_mid.plain) == 30
    assert len(bar_high.plain) == 30

    vu_panel = render_vu_meter(rms_dbfs=-14.5, is_active=True)
    assert isinstance(vu_panel, Panel)
    console.print(vu_panel)

    # 3. Conversation widget
    convo = ConversationBuffer()
    convo.add_user_message("Testing query")
    convo.append_assistant_token("Testing response")
    convo_panel = render_conversation(convo)
    assert isinstance(convo_panel, Panel)
    console.print(convo_panel)

    # 4. Footer widget
    footer_panel = render_footer(state=TUIState.LISTENING)
    assert isinstance(footer_panel, Panel)
    console.print(footer_panel)


def test_tui_app_layout_composition():
    bridge = TUIEventBridge()
    app = VirindaTUIApp(bridge=bridge, model="whisper.cpp", backend="PipeWire", mode="PTT")

    layout = app.compose_layout()
    assert layout is not None

    # Simulate processing incoming events
    bridge.emit_state(TUIState.THINKING, model="gpt-4o-mini", backend="PipeWire")
    bridge.emit_audio_level(rms_dbfs=-18.0)
    bridge.emit_transcript("Open text editor", is_final=True)
    bridge.emit_assistant_delta("Opening editor...")

    app._process_events()

    assert app.current_state == TUIState.THINKING
    assert app.model == "gpt-4o-mini"
    assert app.current_rms_dbfs == -18.0
    assert len(app.conversation.messages) == 2
    assert app.conversation.messages[0].text == "Open text editor"
    assert app.conversation.messages[1].text == "Opening editor..."
