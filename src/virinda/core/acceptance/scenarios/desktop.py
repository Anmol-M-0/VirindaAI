from __future__ import annotations

import tempfile
from pathlib import Path
from time import sleep

from virinda.application.service import AssistantService
from virinda.core.acceptance.models import AcceptanceResult, TurnState
from virinda.core.acceptance.probes import MessageBusProbe, ResourceProbe
from virinda.core.events import InMemoryEventBus
from virinda.core.tokenizer import StreamingSentenceTokenizer
from virinda.core.trace import VoiceTurnResult
from virinda.core.voice import VoiceInteractionController, VoiceSignal
from virinda.core.voice_runtime import VoiceTurnRuntime
from virinda.domain.audio import AudioFrame, AudioPolicy, VoiceActivity
from virinda.infrastructure.persistence.sqlite import SQLiteConversationStore
from virinda.infrastructure.providers.echo import EchoProvider
from virinda.infrastructure.providers.router import StaticProviderRouter


def run_desktop_scenario() -> AcceptanceResult:
    res = AcceptanceResult(scenario="Scenario E: Desktop Web Overlay & OVOS MessageBus Status")
    res.resources_before = ResourceProbe.sample()

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "desktop.sqlite3"
        store = SQLiteConversationStore(db_path)
        bus = InMemoryEventBus()
        router = StaticProviderRouter({"echo": EchoProvider()}, default="echo")
        service = AssistantService(router=router, store=store, event_bus=bus)

        probe = MessageBusProbe()

        def mock_bus_emitter(signal: VoiceSignal) -> None:
            # Map runtime voice signals to standard virinda.voice.state messages
            state_map = {
                "armed": TurnState.CREATED,
                "listening_started": TurnState.LISTENING,
                "speech_started": TurnState.LISTENING,
                "utterance_ready": TurnState.TRANSCRIBING,
                "processing_started": TurnState.THINKING,
                "speaking_started": TurnState.SPEAKING,
                "follow_up_window_open": TurnState.LISTENING,
                "barge_in": TurnState.INTERRUPTING,
                "cancelled": TurnState.CANCELLED,
            }
            if signal.name in state_map:
                state = state_map[signal.name]
                probe.on_event("virinda.voice.state", {"state": state.value, "signal": signal.name})

        class DesktopVad:
            def reset(self):
                pass

            def process(self, frame):
                return VoiceActivity(True)

        class DesktopRecognizer:
            def transcribe(self, frames):
                return "Show desktop overlay status."

        class DesktopTTS:
            def synthesize(self, text):
                return [AudioFrame(b"desktop_audio")]

        class DesktopOutput:
            def play_interruptible(self, frames, *, cancel_event):
                for _ in range(2):
                    if cancel_event.is_set():
                        return
                    sleep(0.005)

            def stop(self):
                pass

        results: list[VoiceTurnResult] = []
        controller = VoiceInteractionController(
            policy=AudioPolicy(min_speech_ms=0, end_silence_ms=0),
            vad=DesktopVad(),
        )
        runtime = VoiceTurnRuntime(
            service=service,
            controller=controller,
            recognizer=DesktopRecognizer(),
            synthesizer=DesktopTTS(),
            output=DesktopOutput(),
            tokenizer=StreamingSentenceTokenizer(),
            emit=mock_bus_emitter,
            on_turn_result=results.append,
        )

        # Turn 1: Normal completed turn
        controller.arm()
        controller.trigger_listening("wake_word")
        controller.on_audio(AudioFrame(b"pcm_frame"), now=0.0)
        controller.push_to_talk_released()

        for _ in range(50):
            if results:
                break
            sleep(0.01)

        # Turn 2: Interrupted turn
        controller.arm()
        controller.trigger_listening("push_to_talk")
        controller.on_audio(AudioFrame(b"pcm_frame"), now=0.0)
        controller.push_to_talk_released()
        sleep(0.01)
        controller.on_wake_while_speaking()

        for _ in range(50):
            if len(results) >= 2:
                break
            sleep(0.01)

        # Assertion 1: MessageBus captured state events
        res.add_assertion(
            "bus_events_captured",
            len(probe.events) >= 5,
            expected=">= 5 events",
            actual=len(probe.events),
        )

        # Assertion 2: All state transitions were legal according to TurnState lifecycle
        res.add_assertion(
            "zero_illegal_transitions",
            len(probe.illegal_transitions) == 0,
            expected=0,
            actual=len(probe.illegal_transitions),
            details=str(probe.illegal_transitions) if probe.illegal_transitions else None,
        )

        # Assertion 3: Results delivered
        res.add_assertion(
            "desktop_turns_completed",
            len(results) == 2,
            expected=2,
            actual=len(results),
        )

        runtime.close()
        service.close()

    res.resources_after = ResourceProbe.sample()
    res.finalize()
    return res
